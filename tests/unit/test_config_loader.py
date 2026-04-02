from src.services.config_loader import load_scan_config


def test_config_loader_reads_scaffold_configs() -> None:
    config = load_scan_config("config")
    assert config.defaults["version"] == "v1-defaults"
    assert config.scoring["scoring"]["total_score_max"] == 100.0
    assert config.universe["universe"]["market"] == "US"
