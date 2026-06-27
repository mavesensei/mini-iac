import pytest
from pathlib import Path
from mini_iac.parser.loader import load_spec
from mini_iac.exceptions import ConfigError


def test_valid_minimal_spec(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text("containers:\n  - name: web\n    image: nginx:1.27\n")
    spec = load_spec(f)
    assert spec.project == "app"
    assert spec.containers[0].name == "web"
    assert spec.containers[0].image == "nginx:1.27"


def test_project_defaults_to_filename_stem(tmp_path):
    f = tmp_path / "my-stack.yaml"
    f.write_text("containers:\n  - name: web\n    image: nginx:1.27\n")
    spec = load_spec(f)
    assert spec.project == "my-stack"


def test_explicit_project_field(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text("project: myapp\ncontainers:\n  - name: web\n    image: nginx:1.27\n")
    spec = load_spec(f)
    assert spec.project == "myapp"


def test_missing_image_raises_config_error(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text("containers:\n  - name: web\n")
    with pytest.raises(ConfigError, match="image"):
        load_spec(f)


def test_duplicate_container_names_raises(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text(
        "containers:\n"
        "  - name: web\n    image: nginx:1.27\n"
        "  - name: web\n    image: nginx:1.26\n"
    )
    with pytest.raises(ConfigError, match="Duplicate container name"):
        load_spec(f)


def test_circular_depends_on_raises(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text(
        "containers:\n"
        "  - name: a\n    image: nginx:1.27\n    depends_on: [b]\n"
        "  - name: b\n    image: nginx:1.27\n    depends_on: [a]\n"
    )
    with pytest.raises(ConfigError, match="Circular"):
        load_spec(f)


def test_var_interpolation_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_SECRET", "s3cr3t")
    f = tmp_path / "app.yaml"
    f.write_text(
        "containers:\n  - name: web\n    image: nginx:1.27\n"
        "    env:\n      SECRET: \"${MY_SECRET}\"\n"
    )
    spec = load_spec(f)
    assert spec.containers[0].env["SECRET"] == "s3cr3t"


def test_var_interpolation_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text("DB_PASS=hunter2\n")
    f = tmp_path / "app.yaml"
    f.write_text(
        "containers:\n  - name: db\n    image: postgres:16\n"
        "    env:\n      POSTGRES_PASSWORD: \"${DB_PASS}\"\n"
    )
    spec = load_spec(f)
    assert spec.containers[0].env["POSTGRES_PASSWORD"] == "hunter2"


def test_env_overrides_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("VAR", "from_env")
    (tmp_path / ".env").write_text("VAR=from_dotenv\n")
    f = tmp_path / "app.yaml"
    f.write_text(
        "containers:\n  - name: web\n    image: nginx:1.27\n"
        "    env:\n      X: \"${VAR}\"\n"
    )
    spec = load_spec(f)
    assert spec.containers[0].env["X"] == "from_env"


def test_missing_variable_raises(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text(
        "containers:\n  - name: web\n    image: nginx:1.27\n"
        "    env:\n      X: \"${UNDEFINED_VAR_XYZ}\"\n"
    )
    with pytest.raises(ConfigError, match="UNDEFINED_VAR_XYZ"):
        load_spec(f)


def test_full_spec_network_and_volumes(tmp_path):
    f = tmp_path / "full.yaml"
    f.write_text(
        "containers:\n"
        "  - name: api\n    image: nginx:1.27\n    depends_on: [db]\n"
        "  - name: db\n    image: postgres:16\n"
        "    volumes:\n      - pg-data:/var/lib/postgresql/data\n"
        "network:\n  name: app-net\n"
        "volumes:\n  - pg-data\n"
    )
    spec = load_spec(f)
    assert spec.network.name == "app-net"
    assert "pg-data" in spec.volumes
    assert spec.containers[0].depends_on == ["db"]
