# Nix / NixOS / nix-darwin integration

This plugin ships with a `flake.nix` that exposes:

- `packages.default` — the plugin as a store-path directory, ready for `~/.claude/settings.json`
- `apps.default` — `classroom` CLI runnable via `nix run`
- `apps.setup-wizard` — guided OAuth setup runnable via `nix run .#setup-wizard`
- `devShells.default` — Python + shellcheck + shfmt + rclone + gh
- `checks.lint` — runs the full shellcheck + shfmt + python syntax suite under `nix flake check`
- `formatter` — `nix fmt` runs `shfmt -w` on all shell scripts

---

## Quick start (no install)

```bash
# One-shot run the CLI without installing anything:
nix run github:yolo-labz/claude-classroom-submit -- help
nix run github:yolo-labz/claude-classroom-submit -- courses --terse

# Run the guided setup wizard:
nix run github:yolo-labz/claude-classroom-submit#setup-wizard
```

These are the fastest way to try the plugin without touching your NixOS / nix-darwin config.

---

## Add as a flake input (nix-darwin)

In your system flake:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    nix-darwin.url = "github:LnL7/nix-darwin";

    claude-classroom-submit = {
      url = "github:yolo-labz/claude-classroom-submit";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, nix-darwin, claude-classroom-submit, ... }: {
    darwinConfigurations.your-hostname = nix-darwin.lib.darwinSystem {
      system = "aarch64-darwin";
      specialArgs = { inherit claude-classroom-submit; };
      modules = [
        ./modules/claude-code.nix
        # … your other modules
      ];
    };
  };
}
```

## Register the plugin in ~/.claude/settings.json

In a nix-darwin module (e.g. `modules/claude-code.nix`):

```nix
{ pkgs, lib, claude-classroom-submit, ... }:

let
  pluginPath = claude-classroom-submit.packages.${pkgs.stdenv.system}.default;
in {
  home.file.".claude/settings.json".text = builtins.toJSON {
    "$schema" = "https://json.schemastore.org/claude-code-settings.json";

    enabledPlugins = {
      "claude-classroom-submit@claude-classroom-submit" = true;
      # … your other plugins
    };

    extraKnownMarketplaces = {
      claude-classroom-submit = {
        source = {
          path = "${pluginPath}";
          source = "directory";
        };
      };
      # … your other marketplaces
    };
  };

  # Optional: also install the CLI binary globally so you can run `classroom`
  # from any shell without going through the Claude Code plugin system.
  home.packages = [
    claude-classroom-submit.packages.${pkgs.stdenv.system}.classroom-cli
  ];
}
```

Rebuild:

```bash
darwin-rebuild switch --flake .
```

After the rebuild, `~/.claude/settings.json` points at the nix store path
(immutable, atomically updated on every rebuild), and `classroom` is
available in your PATH.

## Home-manager (standalone or as a nix-darwin module)

Same pattern, just use `home.file` / `home.packages` in your home-manager
config instead of nix-darwin:

```nix
{ pkgs, claude-classroom-submit, ... }:
{
  home.packages = [
    claude-classroom-submit.packages.${pkgs.stdenv.system}.classroom-cli
  ];

  home.file.".claude/settings.json".source = pkgs.writeText "claude-settings.json" (
    builtins.toJSON {
      enabledPlugins = {
        "claude-classroom-submit@claude-classroom-submit" = true;
      };
      extraKnownMarketplaces = {
        claude-classroom-submit = {
          source = {
            path = "${claude-classroom-submit.packages.${pkgs.stdenv.system}.default}";
            source = "directory";
          };
        };
      };
    }
  );
}
```

## Plain NixOS (no home-manager)

```nix
{ pkgs, claude-classroom-submit, ... }:
{
  environment.systemPackages = [
    claude-classroom-submit.packages.${pkgs.stdenv.system}.classroom-cli
  ];
}
```

Register the plugin manually in `~/.claude/settings.json` or use an activation
script to write it.

## Merging with an existing settings.json

If you already have a long `~/.claude/settings.json` managed by nix (as in
the claude-mac-chrome setup), just add two keys to the existing attribute set:

```nix
enabledPlugins = existing.enabledPlugins // {
  "claude-classroom-submit@claude-classroom-submit" = true;
};

extraKnownMarketplaces = existing.extraKnownMarketplaces // {
  claude-classroom-submit = {
    source = {
      path = "${claude-classroom-submit.packages.${pkgs.stdenv.system}.default}";
      source = "directory";
    };
  };
};
```

## Development shell

Clone the repo and `nix develop` to get all the tools you need to hack on
the plugin:

```bash
git clone https://github.com/yolo-labz/claude-classroom-submit
cd claude-classroom-submit
nix develop

# You now have python3, shellcheck, shfmt, rclone, gh in PATH
./scripts/lint.sh
```

## CI / flake check

The package's `checkPhase` runs the full lint suite (shfmt + shellcheck +
py_compile) in the Nix build sandbox. You can surface it in CI with:

```bash
nix flake check
```

This builds the plugin (which runs the checks) and exits non-zero on any
lint failure.

## Update the flake lock

To pull the latest version of the plugin:

```bash
nix flake lock --update-input claude-classroom-submit
darwin-rebuild switch --flake .
```

## Version pinning

Flake inputs can be pinned to a specific tag or commit:

```nix
claude-classroom-submit = {
  url = "github:yolo-labz/claude-classroom-submit/v0.1.0";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

or:

```nix
claude-classroom-submit = {
  url = "github:yolo-labz/claude-classroom-submit?rev=6fee228abc...";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

## Troubleshooting

**`error: missing input 'flake-utils'`** — your flake.lock is stale. Run `nix flake update` in the consuming flake.

**`nix flake check` fails with `shellcheck: unknown flag -o all`** — your shellcheck is very old (pre-0.5). Update nixpkgs.

**Claude Code doesn't see the plugin after rebuild** — restart your Claude Code session. Settings are only re-read at session startup. If still missing, verify the marketplace path exists: `ls $(nix eval --raw .#packages.aarch64-darwin.default)/.claude-plugin/marketplace.json`.
