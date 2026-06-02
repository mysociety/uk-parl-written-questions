import typer

from .fetch import create_dataset, enrich_truncated_questions, get_all_data

app = typer.Typer()


def main():
    app()


@app.command()
def fetch():
    get_all_data(force_recent=True)


@app.command()
def enrich():
    data = get_all_data()
    enrich_truncated_questions(data)


@app.command()
def create():
    create_dataset()


if __name__ == "__main__":
    main()
