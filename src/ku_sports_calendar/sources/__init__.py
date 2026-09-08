from .ku_sidearm import KuSidearmScheduleSource, KuSidearmFootballSource


def build_source(config: dict):
    source_type = config.get("source_type", "ku_sidearm")
    if source_type == "ku_sidearm":
        return KuSidearmScheduleSource(config)
    raise ValueError(f"Unsupported source_type: {source_type}")


__all__ = ["KuSidearmScheduleSource", "KuSidearmFootballSource", "build_source"]
