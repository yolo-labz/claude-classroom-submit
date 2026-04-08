{
  description = "claude-classroom-submit — autonomous Google Classroom submission plugin for Claude Code (Classroom REST API + OAuth 2.0 Installed App flow, pure Python stdlib, zero dependencies)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      version = "0.1.0";

      # The plugin derivation — copies the repository layout that Claude Code
      # expects (.claude-plugin/, commands/, skills/, scripts/, docs/) into
      # $out so nix-darwin / home-manager can reference a stable store path
      # from ~/.claude/settings.json's `extraKnownMarketplaces`.
      #
      # This matches the pattern used by `claude-mac-chrome` for the
      # `settings.extraKnownMarketplaces.<name>.source.path` field.
      classroom-plugin = pkgs.stdenvNoCC.mkDerivation {
        pname = "claude-classroom-submit";
        inherit version;
        src = self;
        dontBuild = true;
        dontConfigure = true;
        # Lint during the build sandbox. Keeps shellcheck + shfmt + python
        # syntax regressions from reaching the store.
        nativeBuildInputs = with pkgs; [shellcheck shfmt python3];
        doCheck = true;
        checkPhase = ''
          runHook preCheck
          echo "→ shfmt -d (formatting)"
          shfmt -d -i 0 -ci -bn \
            skills/classroom-submit/classroom-lib.sh \
            scripts/lint.sh \
            scripts/setup-wizard.sh
          echo "→ shellcheck"
          shellcheck -x -o all -e SC2250,SC2312,SC2310 \
            skills/classroom-submit/classroom-lib.sh \
            scripts/lint.sh \
            scripts/setup-wizard.sh
          echo "→ python3 -m py_compile"
          PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile skills/classroom-submit/classroom.py
          runHook postCheck
        '';
        installPhase = ''
          runHook preInstall
          mkdir -p $out
          cp -r .claude-plugin $out/
          cp -r commands $out/
          cp -r skills $out/
          cp -r scripts $out/
          cp -r docs $out/
          install -m 0644 README.md CHANGELOG.md CLAUDE.md LICENSE $out/
          chmod 0755 \
            $out/skills/classroom-submit/classroom-lib.sh \
            $out/skills/classroom-submit/classroom.py \
            $out/scripts/lint.sh \
            $out/scripts/setup-wizard.sh
          runHook postInstall
        '';
        meta = with pkgs.lib; {
          description = "Autonomous Google Classroom submission plugin for Claude Code";
          longDescription = ''
            Bypasses the cross-origin Drive Picker iframe that blocks browser
            automation of Google Classroom by speaking the Classroom REST API
            directly. Pure Python stdlib (no google-auth, no google-api-python-
            client). OAuth 2.0 Installed App flow with loopback redirect,
            automatic access-token refresh, atomic
            modifyAttachments + turnIn, rclone-native upload path. Ships with
            three Claude Code slash commands and a SKILL.md that auto-triggers
            on "submit to Classroom" intents.
          '';
          homepage = "https://github.com/yolo-labz/claude-classroom-submit";
          license = licenses.mit;
          platforms = platforms.darwin ++ platforms.linux;
          maintainers = [];
          mainProgram = "classroom-lib.sh";
        };
      };

      # A thin writeShellApplication wrapper so users can `nix run` the CLI
      # directly without knowing the internal path inside the plugin.
      classroom-cli = pkgs.writeShellApplication {
        name = "classroom";
        runtimeInputs = with pkgs; [python3 rclone];
        text = ''
          exec ${classroom-plugin}/skills/classroom-submit/classroom-lib.sh "$@"
        '';
      };
    in {
      # ---------------------------------------------------------------------
      # packages
      # ---------------------------------------------------------------------
      packages = {
        default = classroom-plugin;
        claude-classroom-submit = classroom-plugin;
        classroom-cli = classroom-cli;
      };

      # ---------------------------------------------------------------------
      # apps — `nix run github:yolo-labz/claude-classroom-submit -- <cmd>`
      # ---------------------------------------------------------------------
      apps = {
        default = {
          type = "app";
          program = "${classroom-cli}/bin/classroom";
        };
        classroom = {
          type = "app";
          program = "${classroom-cli}/bin/classroom";
        };
        setup-wizard = {
          type = "app";
          program = "${classroom-plugin}/scripts/setup-wizard.sh";
        };
      };

      # ---------------------------------------------------------------------
      # devShell — tools needed to hack on the plugin itself
      # ---------------------------------------------------------------------
      devShells.default = pkgs.mkShell {
        name = "claude-classroom-submit-dev";
        packages = with pkgs; [
          python3
          shellcheck
          shfmt
          rclone
          gh
        ];
        shellHook = ''
          echo "claude-classroom-submit dev shell"
          echo "  ./scripts/lint.sh        — run the full lint suite"
          echo "  ./scripts/setup-wizard.sh — guided Google Cloud OAuth setup"
          echo ""
        '';
      };

      # ---------------------------------------------------------------------
      # checks — surfaced by `nix flake check`
      # ---------------------------------------------------------------------
      checks = {
        # Re-expose the build (which includes shellcheck + shfmt + py_compile
        # via checkPhase) as a named check so `nix flake check` catches it.
        lint = classroom-plugin;
      };

      # ---------------------------------------------------------------------
      # formatter — `nix fmt` auto-formats shell scripts
      # ---------------------------------------------------------------------
      formatter = pkgs.writeShellApplication {
        name = "claude-classroom-submit-fmt";
        runtimeInputs = [pkgs.shfmt];
        text = ''
          exec shfmt -w -i 0 -ci -bn \
            skills/classroom-submit/classroom-lib.sh \
            scripts/lint.sh \
            scripts/setup-wizard.sh
        '';
      };
    });
}
