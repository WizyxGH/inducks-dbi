"""Vision-based Disney character appearance (xapp) detection for unpublished covers.

Uses YOLOv8 + DINOv2 embeddings (``character_embeddings.npz``) to identify
Inducks character codes on a cover image when the cover is inédit (unknown
storycode). Heavy ML dependencies (torch, ultralytics, numpy) are imported
lazily so environments without them (e.g. lightweight CI) gracefully return [].
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional, Union

LIVING_CLASSES = {"person", "bird", "cat", "dog", "teddy bear", "horse", "sheep", "cow", "bear"}
MAJOR_DISNEY_CHARACTERS = {
    "DD", "US", "HDL", "DA", "FE", "GL", "GY", "MM", "GO", "PL",
    "MI", "CL", "HH", "PE", "PB", "PK", "BB", "MDS", "RKD", "LVD",
    "GD", "GU", "Battista", "Lusky", "FZ", "IP", "CAS", "OH", "TR", "RS",
}

_DETECTOR_CACHE: dict[tuple[str, str], object] = {}
_DINOV2_CACHE: dict[str, tuple[object, object, str]] = {}
_COVER_INDEX_CACHE: dict[str, object] = {}


def _get_dinov2(device: Optional[str] = None):
    """Loads and caches (model, transform, device) once per process."""
    import torch
    from torchvision import transforms

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    if dev not in _DINOV2_CACHE:
        model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", verbose=False)
        model.eval().to(dev)
        tfm = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        _DINOV2_CACHE[dev] = (model, tfm, dev)
    return _DINOV2_CACHE[dev]


def _default_cover_index_path() -> Optional[Path]:
    env_cov = os.environ.get("INDUCKS_COVER_INDEX_PATH")
    models_dir = Path(__file__).resolve().parents[3] / "transcript" / "pipeline" / "models"
    cov_path = Path(env_cov) if env_cov else (models_dir / "cover_embeddings.npz")
    return cov_path if cov_path.exists() else None


def _default_model_paths() -> tuple[Optional[Path], Optional[Path]]:
    """Locates character_embeddings.npz and yolov8n.pt from env or sibling transcript app."""
    env_idx = os.environ.get("INDUCKS_VISION_INDEX_PATH")
    env_yolo = os.environ.get("INDUCKS_VISION_YOLO_PATH")

    # Sibling monorepo layout: apps/inducks-dbi/src/inducks_dbi/vision.py -> apps/transcript/pipeline/models/
    models_dir = Path(__file__).resolve().parents[3] / "transcript" / "pipeline" / "models"
    idx_path = Path(env_idx) if env_idx else (models_dir / "character_embeddings.npz")
    yolo_path = Path(env_yolo) if env_yolo else (models_dir / "yolov8n.pt")
    return (
        idx_path if idx_path.exists() else None,
        yolo_path if yolo_path.exists() else None,
    )


class CoverCharacterDetector:
    """Lazy-loaded YOLO + DINOv2 character detector for cover images."""

    def __init__(self, index_path: Path, yolo_model_path: Optional[Path] = None):
        import numpy as np
        import torch
        from torchvision import transforms

        self.np = np
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        data = np.load(str(index_path), allow_pickle=True)
        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"].tolist()
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.norm_embeddings = self.embeddings / np.maximum(norms, 1e-8)

        self.model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", verbose=False)
        self.model.eval().to(self.device)
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        self.yolo_model = None
        if yolo_model_path and yolo_model_path.exists():
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO(str(yolo_model_path))
            except Exception:
                pass

    def _match_crop(self, crop_img, min_score: float = 0.70) -> Optional[tuple[str, float]]:
        tensor = self.transform(crop_img).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            emb = self.model(tensor).cpu().numpy()[0]
        emb = emb / max(float(self.np.linalg.norm(emb)), 1e-8)
        sims = self.np.dot(self.norm_embeddings, emb)

        top_indices = self.np.argsort(sims)[::-1][:10]
        hero_scores: dict[str, float] = {}
        for idx in top_indices:
            sim = float(sims[idx])
            if sim < min_score:
                continue
            code = str(self.metadata[idx].get("hero", "")).strip()
            if not code:
                continue
            boosted = sim * (1.03 if code in MAJOR_DISNEY_CHARACTERS else 1.0)
            if boosted > hero_scores.get(code, 0.0):
                hero_scores[code] = boosted

        if not hero_scores:
            return None
        best_code = max(hero_scores, key=hero_scores.get)
        return best_code, hero_scores[best_code]

    def detect(self, image: Union[bytes, str, Path], min_score: float = 0.70) -> list[str]:
        from PIL import Image

        if isinstance(image, (bytes, bytearray)):
            im = Image.open(io.BytesIO(image)).convert("RGB")
        else:
            im = Image.open(image).convert("RGB")

        pw, ph = im.size
        # Focus below the top magazine masthead band (y >= 15%)
        work_im = im.crop((0, int(ph * 0.15), pw, ph))
        ww, wh = work_im.size

        crops = []
        if self.yolo_model:
            try:
                results = self.yolo_model(work_im, conf=0.10, verbose=False)
                for r in results:
                    for b in r.boxes:
                        name = self.yolo_model.names[int(b.cls[0])]
                        if name in LIVING_CLASSES:
                            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                            if (x2 - x1) >= 30 and (y2 - y1) >= 30:
                                bw, bh = x2 - x1, y2 - y1
                                crops.append(work_im.crop((
                                    max(0, int(x1 - 0.15 * bw)),
                                    max(0, int(y1 - 0.15 * bh)),
                                    min(ww, int(x2 + 0.15 * bw)),
                                    min(wh, int(y2 + 0.15 * bh)),
                                )))
            except Exception:
                pass

        if len(crops) < 2 and ww >= 200 and wh >= 200:
            for wf, hf in ((0.35, 0.35), (0.45, 0.45)):
                cw, ch = int(ww * wf), int(wh * hf)
                sx, sy = max(1, cw // 2), max(1, ch // 2)
                for y in range(0, max(1, wh - ch + 1), sy):
                    for x in range(0, max(1, ww - cw + 1), sx):
                        crops.append(work_im.crop((x, y, x + cw, y + ch)))

        found: dict[str, float] = {}
        for crop in crops:
            res = self._match_crop(crop, min_score=min_score)
            if res:
                code, score = res
                if score > found.get(code, 0.0):
                    found[code] = score

        return sorted(found.keys(), key=lambda c: found[c], reverse=True)


def detect_cover_characters(
    image: Union[bytes, str, Path],
    index_path: Optional[Union[str, Path]] = None,
    yolo_model_path: Optional[Union[str, Path]] = None,
    min_score: float = 0.72,
) -> list[str]:
    """Detects Inducks character codes (xapp) on a cover image.

    Returns an empty list gracefully if vision dependencies or model files are unavailable.
    """
    default_idx, default_yolo = _default_model_paths()
    idx = Path(index_path) if index_path else default_idx
    yolo = Path(yolo_model_path) if yolo_model_path else default_yolo
    if not idx or not idx.exists():
        return []

    key = (str(idx), str(yolo or ""))
    try:
        detector = _DETECTOR_CACHE.get(key)
        if detector is None:
            detector = CoverCharacterDetector(idx, yolo)
            _DETECTOR_CACHE[key] = detector
        return detector.detect(image, min_score=min_score)
    except Exception:
        return []


def _artwork_crop(im, box=(0.1, 0.3, 0.9, 0.9)):
    """Crops out the magazine logo band and outer margins, matching covers.ARTWORK."""
    w, h = im.size
    return im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))


class CoverEmbeddingIndex:
    """Global DINOv2 cosine-similarity index over Inducks cover scans (What-The-Duck style)."""

    def __init__(self, index_path: Path):
        import numpy as np

        self.np = np
        data = np.load(str(index_path), allow_pickle=True)
        self.embeddings = data["embeddings"]
        self.storycodes = data["storycodes"].tolist()
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.norm_embeddings = self.embeddings / np.maximum(norms, 1e-8)
        self.model, self.transform, self.device = _get_dinov2()

    def search(self, image: Union[bytes, str, Path], min_score: float = 0.84, min_margin: float = 0.04) -> tuple[Optional[str], list[tuple[float, str]]]:
        import torch
        from PIL import Image

        if isinstance(image, (bytes, bytearray)):
            im = Image.open(io.BytesIO(image)).convert("RGB")
        else:
            im = Image.open(image).convert("RGB")

        crop = _artwork_crop(im)
        tensor = self.transform(crop).unsqueeze(0).to(self.device)
        with torch.no_grad():
            emb = self.model(tensor).cpu().numpy()[0]
        emb = emb / max(float(self.np.linalg.norm(emb)), 1e-8)
        sims = self.np.dot(self.norm_embeddings, emb)

        top_k = self.np.argsort(sims)[::-1][:20]
        best_by_code: dict[str, float] = {}
        for idx in top_k:
            code = str(self.storycodes[idx]).strip()
            score = round(float(sims[idx]), 3)
            if code and score > best_by_code.get(code, 0.0):
                best_by_code[code] = score

        ranked = sorted(((score, code) for code, score in best_by_code.items()), reverse=True)
        if ranked and ranked[0][0] >= min_score and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= min_margin):
            return ranked[0][1], ranked
        return None, ranked


def find_cover_by_embedding(
    image: Union[bytes, str, Path],
    index_path: Optional[Union[str, Path]] = None,
    min_score: float = 0.84,
    min_margin: float = 0.04,
) -> tuple[Optional[str], list[tuple[float, str]]]:
    """Matches a cover image against the global DINOv2 cover index (if built)."""
    idx = Path(index_path) if index_path else _default_cover_index_path()
    if not idx or not idx.exists():
        return None, []
    try:
        key = str(idx)
        index = _COVER_INDEX_CACHE.get(key)
        if index is None:
            index = CoverEmbeddingIndex(idx)
            _COVER_INDEX_CACHE[key] = index
        return index.search(image, min_score=min_score, min_margin=min_margin)
    except Exception:
        return None, []


def build_cover_index(query, fetch, output_path: Union[str, Path], limit: int = 20000, log=print) -> int:
    """Builds or refreshes ``cover_embeddings.npz`` from recent Inducks webusers cover scans."""
    import numpy as np
    import torch
    from PIL import Image

    rows = query(
        "SELECT e.storycode, e.url FROM inducks_entryurl e "
        "JOIN inducks_entry en ON en.entrycode = e.entrycode "
        "WHERE e.sitecode = 'webusers' AND e.pagenumber = '1' AND en.position = 'a' "
        "AND e.storycode IS NOT NULL AND e.storycode <> '' "
        "ORDER BY e.url DESC LIMIT ?",
        (limit,),
    ) or []

    if not rows:
        return 0

    model, transform, device = _get_dinov2()
    embs = []
    codes = []
    for storycode, url_path in rows:
        url = f"https://inducks.org/hr.php?image=https://outducks.org/webusers/webusers/{url_path}&normalsize=1"
        try:
            data = fetch(url)
            if not data:
                continue
            im = Image.open(io.BytesIO(data)).convert("RGB")
            tensor = transform(_artwork_crop(im)).unsqueeze(0).to(device)
            with torch.no_grad():
                emb = model(tensor).cpu().numpy()[0].astype(np.float32)
            embs.append(emb)
            codes.append(storycode)
        except Exception:
            continue

    if not embs:
        return 0

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(out), embeddings=np.stack(embs), storycodes=np.array(codes))
    log(f"[cover-index] Saved {len(codes)} cover embeddings to {out}")
    return len(codes)
