import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "scripts"))

from scripts.import_real_data import validate_robots
from scripts.validate_robots_catalog import validate_rows, EXPECTED


def make_robot_row(sku="ROBOT-1", image_url=""):
    return {
        "sku_code": sku,
        "name": "Test Robot",
        "manufacturer": "Test Mfr",
        "category": "AMR",
        "price": "100000",
        "image_url": image_url,
    }


def test_import_real_data_accepts_valid_image_urls():
    valid_urls = [
        "http://example.com/robot.jpg",
        "https://cdn.pudurobotics.com/img.png",
        "/robots/pudu-t300.png",
        "",
        None,
    ]
    for url in valid_urls:
        rows = [make_robot_row("ROBOT-A", url or "")]
        errors, _ = validate_robots(rows, data_source="real")
        assert not any("image_url" in e for e in errors), f"Should accept '{url}', but got: {errors}"


def test_import_real_data_rejects_invalid_image_urls():
    invalid_urls = [
        "ftp://example.com/robot.jpg",
        "javascript:alert(1)",
        "relative/path/robot.jpg",
        "/static/robot.jpg",
        "robots/pudu-t300.png",
        "data:image/png;base64,123",
    ]
    for url in invalid_urls:
        rows = [make_robot_row("ROBOT-B", url)]
        errors, _ = validate_robots(rows, data_source="real")
        assert any("image_url" in e for e in errors), f"Should reject '{url}', but passed"


def test_validate_robots_catalog_accepts_valid_image_urls():
    valid_urls = [
        "http://example.com/robot.jpg",
        "https://cdn.pudurobotics.com/img.png",
        "/robots/pudu-t300.png",
        "",
    ]
    for url in valid_urls:
        rows = [make_robot_row("ROBOT-C", url)]
        blockers, _ = validate_rows(rows)
        assert not any("image_url" in b for b in blockers), f"Should accept '{url}', but got: {blockers}"


def test_validate_robots_catalog_rejects_invalid_image_urls():
    invalid_urls = [
        "ftp://example.com/robot.jpg",
        "javascript:alert(1)",
        "relative/path/robot.jpg",
        "/static/robot.jpg",
        "robots/pudu-t300.png",
        "data:image/png;base64,123",
    ]
    for url in invalid_urls:
        rows = [make_robot_row("ROBOT-D", url)]
        blockers, _ = validate_rows(rows)
        assert any("image_url" in b for b in blockers), f"Should reject '{url}', but passed"
