import typer

from .fetch import create_dataset, enrich_truncated_questions, get_all_data
from .holidays import refresh_bank_holidays

app = typer.Typer()


def main():
    app()


@app.command()
def fetch():
    refresh_bank_holidays()
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
