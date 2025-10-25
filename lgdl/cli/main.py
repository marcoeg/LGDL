import click, json, re
from lgdl.parser.parser import parse_lgdl
from lgdl.parser.ir import compile_game

@click.group()
def cli(): ...

@cli.command()
@click.argument("path")
def validate(path):
    g = parse_lgdl(path)
    if not g.moves:
        raise SystemExit("No moves found")
    click.echo("OK")

@cli.command()
@click.argument("path")
@click.option("-o","--out", default="out.ir.json")
def compile(path, out):
    g = parse_lgdl(path)
    ir = compile_game(g)
    def _default(obj):
        if isinstance(obj, re.Pattern):
            return obj.pattern
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

    with open(out,"w") as f:
        json.dump(ir, f, indent=2, default=_default)
    click.echo(f"Wrote {out}")

@cli.command()
@click.option(
    "--games",
    required=True,
    help="Comma-separated game_id:path pairs (e.g., 'medical:examples/medical/game.lgdl')"
)
@click.option("--port", default=8000, help="Server port")
@click.option("--dev", is_flag=True, help="Enable dev mode (hot reload)")
def serve(games: str, port: int, dev: bool):
    """
    Start API server with multiple games.

    Example:

        lgdl serve --games medical:examples/medical/game.lgdl,er:examples/er_triage.lgdl
    """
    import os, uvicorn
    from pathlib import Path

    # Validate game specs before starting server
    click.echo("Validating game files...")
    for pair in games.split(","):
        if ":" not in pair:
            click.echo(
                f"Error: Invalid format '{pair}'. Expected 'game_id:path'",
                err=True
            )
            raise click.Abort()

        game_id, path = pair.split(":", 1)
        path_obj = Path(path.strip())

        if not path_obj.exists():
            click.echo(f"Error: Game file not found: {path}", err=True)
            raise click.Abort()

        click.echo(f"✓ Validated: {game_id.strip()} -> {path_obj.absolute()}")

    # Set env vars for startup
    os.environ["LGDL_GAMES"] = games
    if dev:
        os.environ["LGDL_DEV_MODE"] = "1"
        click.echo("⚡ Dev mode enabled (hot reload available)")

    click.echo(f"\nStarting LGDL API server on port {port}...")
    click.echo(f"Health check: http://127.0.0.1:{port}/healthz")
    click.echo(f"Games list: http://127.0.0.1:{port}/games\n")

    from lgdl.runtime.api import app
    uvicorn.run(app, host="0.0.0.0", port=port, reload=dev)

if __name__ == "__main__":
    cli()
