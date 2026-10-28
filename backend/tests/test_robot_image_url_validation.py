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


def test_components_robot_image_fallback_and_attributes():
    component_files = [
        root_dir / "components" / "pipeline" / "pixelated-image-canvas.tsx",
        root_dir / "components" / "portal" / "tabs" / "catalog-tab.tsx",
        root_dir / "components" / "portal" / "tabs" / "matches-tab.tsx",
        root_dir / "components" / "portal" / "tabs" / "demos-tab.tsx",
    ]
    for cf in component_files:
        assert cf.exists(), f"{cf} does not exist"
        content = cf.read_text(encoding="utf-8")
        assert 'referrerPolicy="no-referrer"' in content, f"{cf.name} missing referrerPolicy"
        assert "loading=\"lazy\"" in content or "loading='lazy'" in content, f"{cf.name} missing lazy loading"
        assert "onError" in content, f"{cf.name} missing onError fallback handler"
        assert "Bot" in content, f"{cf.name} missing Bot placeholder icon"


def test_check_links_detects_broken_urls():
    from scripts.fetch_robot_images import check_links

    rows = [
        {"sku_code": "ROBOT-OK", "image_url": "https://example.com/good.jpg"},
        {"sku_code": "ROBOT-BAD", "image_url": "https://example.com/broken.jpg"},
        {"sku_code": "ROBOT-LOCAL", "image_url": "/robots/test.jpg"},
    ]

    def mock_getter(url):
        if "broken" in url:
            raise OSError("404 Not Found")
        # return a valid jpeg exceeding MIN_BYTES (5000)
        return b"\xff\xd8\xff\xe0" + b"\x00" * 6000

    broken = check_links(rows, mock_getter)
    assert broken == ["ROBOT-BAD"]

