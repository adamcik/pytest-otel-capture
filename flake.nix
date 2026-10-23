{
  description = "pytest-otel-capture development and package checks";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
    nix-tooling.url = "github:adamcik/nix-tooling";
    nix-tooling.inputs.nixpkgs.follows = "nixpkgs";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{
      flake-parts,
      nix-tooling,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" ];
      imports = [
        nix-tooling.flakeModules.formatting.common
        nix-tooling.flakeModules.formatting.python
      ];
      perSystem =
        { pkgs, ... }:
        let
          inherit (pkgs) lib;
          project = "pytest-otel-capture";
          workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
          mkPythonSet =
            python: group:
            (pkgs.callPackage pyproject-nix.build.packages { inherit python; }).overrideScope (
              lib.composeManyExtensions [
                pyproject-build-systems.overlays.default
                (workspace.mkPyprojectOverlay {
                  sourcePreference = "wheel";
                  # Resolve only one of the lockfile's conflicting SDK groups.
                  dependencies = {
                    ${project} = [ group ];
                  };
                })
              ]
            );
          python = pkgs.python312;
          pythonSet = mkPythonSet python "dev";
          devVenv = pythonSet.mkVirtualEnv "${project}-checks" { ${project} = [ "dev" ]; };
          editableSet = pythonSet.overrideScope (
            workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; }
          );
          editableVenv = editableSet.mkVirtualEnv "${project}-dev" { ${project} = [ "dev" ]; };
          mkCheck =
            venv: name: body:
            pkgs.runCommand "${project}-${name}"
              {
                src = ./.;
                nativeBuildInputs = [
                  venv
                  pkgs.uv
                ];
              }
              ''
                cp -r "$src" source
                chmod -R u+w source
                cd source
                export HOME="$TMPDIR"
                export UV_PYTHON="${venv}/bin/python"
                export UV_PYTHON_DOWNLOADS=never
                ${body}
                touch "$out"
              '';
          pythonVersions = {
            python312 = pkgs.python312;
            python313 = pkgs.python313;
            python314 = pkgs.python314;
          };
          otelVersions = {
            otel143 = {
              group = "dev";
              sdk = "1.43.0";
              instrumentation = "0.64b0";
            };
            otel144 = {
              group = "otel144";
              sdk = "1.44.0";
              instrumentation = "0.65b0";
            };
          };
          compatibilityChecks = lib.concatMapAttrs (
            pythonName: interpreter:
            lib.mapAttrs' (
              otelName: otel:
              let
                name = "${pythonName}-${otelName}";
                packageSet = mkPythonSet interpreter otel.group;
                venv = packageSet.mkVirtualEnv "${project}-${name}" { ${project} = [ otel.group ]; };
              in
              lib.nameValuePair name (
                mkCheck venv name ''
                  python - <<'PY'
                  import importlib.metadata as metadata
                  import sys
                  import pytest_otel_capture as capture

                  assert metadata.version("opentelemetry-api") == "${otel.sdk}"
                  assert metadata.version("opentelemetry-sdk") == "${otel.sdk}"
                  assert metadata.version("opentelemetry-instrumentation-logging") == "${otel.instrumentation}"
                  assert sys.version_info[:2] == tuple(map(int, "${interpreter.pythonVersion}".split(".")))
                  assert "site-packages" in capture.__file__
                  PY
                  pytest -q -n 2 -o cache_dir="$TMPDIR/pytest-cache"
                  basedpyright --pythonpath "${venv}/bin/python"
                ''
              )
            ) otelVersions
          ) pythonVersions;
        in
        {
          packages.default = pythonSet.${project};
          checks = {
            package = pythonSet.${project};
            lock = mkCheck devVenv "lock" "uv lock --check --offline";
            tests = compatibilityChecks.python312-otel143;
            typing = mkCheck devVenv "typing" "basedpyright";
            distributions =
              pkgs.runCommand "${project}-distributions"
                {
                  src = ./.;
                  nativeBuildInputs = [ devVenv ];
                }
                ''
                  cp -r "$src" source
                  chmod -R u+w source
                  cd source
                  export HOME="$TMPDIR"
                  python -m build --no-isolation --outdir "$out"
                  twine check "$out"/*
                '';
          }
          // compatibilityChecks;
          devShells.default = pkgs.mkShell {
            packages = [
              editableVenv
              pkgs.uv
            ];
            env = {
              UV_NO_SYNC = "1";
              UV_NO_MANAGED_PYTHON = "1";
              UV_PYTHON = python.interpreter;
              UV_PYTHON_DOWNLOADS = "never";
            };
            shellHook = ''
              unset PYTHONPATH
              export REPO_ROOT=$(git rev-parse --show-toplevel)
            '';
          };
        };
    };
}
