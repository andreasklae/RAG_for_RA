from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceInfo:
    provider: str  # e.g. "Riksantikvaren"
    dataset: str  # e.g. "kulturminner" / "brukerminner"
    collection: str  # e.g. "kulturminner" / "sikringssoner" / ArcGIS layer name
    license_name: str | None = None  # e.g. "NLOD", "CC BY"
    license_url: str | None = None
    api_url: str | None = None  # canonical feature URL when available
    web_url: str | None = None  # human-facing page when available


@dataclass
class RagDocument:
    """
    Normalized document representation for upload/search.
    """

    doc_id: str
    title: str
    text: str
    language: str = "no"
    source: SourceInfo = field(default_factory=lambda: SourceInfo(provider="", dataset="", collection=""))
    tags: list[str] = field(default_factory=list)
    geojson_geometry: dict[str, Any] | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = asdict(self.source)
        return d


def _clean_text(s: str) -> str:
    return " ".join(s.split())


def feature_to_document(
    *,
    dataset: str,
    collection: str,
    feature: dict[str, Any],
    license_name: str | None = None,
    license_url: str | None = None,
) -> RagDocument:
    """
    Convert a GeoJSON Feature from api.ra.no into a retrieval document.
    This is intentionally heuristic and will evolve as we learn the schemas.
    """
    props = dict(feature.get("properties") or {})
    feat_id = str(feature.get("id") or props.get("id") or "")
    if not feat_id:
        feat_id = f"{dataset}:{collection}:{hash(str(props))}"

    title = (
        props.get("tittel")
        or props.get("navn")
        or props.get("gårdsnavn")
        or props.get("enkeltminneart")
        or props.get("lokalitetsart")
        or feat_id
    )
    title = _clean_text(str(title))

    parts: list[str] = []
    for key in [
        "beskrivelse",
        "informasjon",
        "kulturminnesøk",
        "datering",
        "vernetype",
        "vernelov",
        "kommune",
        "fylke",
    ]:
        val = props.get(key)
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            parts.append(f"{key}: {val}")
    text = _clean_text("\n".join(parts)) if parts else title

    web_url = props.get("linkKulturminnesøk") or props.get("linkkulturminnesok") or props.get("linkAskeladden")
    src = SourceInfo(
        provider="Riksantikvaren",
        dataset=dataset,
        collection=collection,
        license_name=license_name,
        license_url=license_url,
        web_url=web_url,
    )

    tags: list[str] = []
    for key in [
        "minnetype",
        "enkeltminnekategori",
        "lokalitetskategori",
        "enkeltminneart",
        "lokalitetsart",
        "vernetype",
    ]:
        v = props.get(key)
        if isinstance(v, str) and v.strip():
            tags.append(v.strip())

    return RagDocument(
        doc_id=f"{dataset}:{collection}:{feat_id}",
        title=title,
        text=text,
        source=src,
        tags=tags,
        geojson_geometry=feature.get("geometry"),
        properties=props,
    )


def arcgis_feature_to_document(
    *,
    dataset: str,
    layer_name: str,
    feature: dict[str, Any],
    license_name: str | None = None,
    license_url: str | None = None,
) -> RagDocument:
    attrs = dict(feature.get("attributes") or {})
    geom = feature.get("geometry")

    feat_id = str(attrs.get("OBJECTID") or attrs.get("objectid") or attrs.get("id") or "")
    if not feat_id:
        feat_id = f"{dataset}:{layer_name}:{hash(str(attrs))}"

    title = (
        attrs.get("navn")
        or attrs.get("tittel")
        or attrs.get("KULTURMINNE")
        or attrs.get("LOKALITET")
        or feat_id
    )
    title = _clean_text(str(title))

    parts: list[str] = []
    for key in ["BESKRIVELSE", "beskrivelse", "INFORMASJON", "informasjon", "KOMMUNE", "kommune", "FYLKE", "fylke"]:
        val = attrs.get(key)
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            parts.append(f"{key}: {val}")
    text = _clean_text("\n".join(parts)) if parts else title

    src = SourceInfo(
        provider="Riksantikvaren",
        dataset=dataset,
        collection=layer_name,
        license_name=license_name,
        license_url=license_url,
    )

    return RagDocument(
        doc_id=f"{dataset}:{layer_name}:{feat_id}",
        title=title,
        text=text,
        source=src,
        tags=[],
        geojson_geometry=geom,
        properties=attrs,
    )


