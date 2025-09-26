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

if __name__ == "__main__":
    cli()
