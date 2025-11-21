
# uk-parl-written-questions

[![badge](https://mybinder.org/badge.svg)](https://mybinder.org/v2/gh/mysociety/uk-parl-written-questions/HEAD)

Dataset view of questions

This repository is available online at https://github.com/mysociety/uk-parl-written-questions

If Github Pages are enabled, the URL is: https://mysociety.github.io/uk-parl-written-questions/

## Data Build Process

To avoid GitHub's repository size limits, this project uses a two-stage data storage approach:

- **Raw data**: Monthly JSON files are stored in `data/raw/commons/` and committed to git for efficient caching
- **Processed datasets**: Large parquet files (`written_questions.parquet` and `written_questions_interests.parquet`) are generated during the build process and not committed to git

### Local Development

To build the datasets locally:

```bash
# Fetch latest data (updates recent months)
python -m src.uk_parl_written_questions fetch

# Generate parquet files from raw data
python -m src.uk_parl_written_questions create
```

The generated parquet files will be created in:
- `data/packages/commons_written_questions/written_questions.parquet`
- `data/packages/commons_written_questions_interests/written_questions_interests.parquet`

### Automated Build

The GitHub Actions workflow automatically:
1. Fetches the latest data
2. Generates the parquet files
3. Builds and publishes the website

Instructions on using the features of this notebook (data publishing, notebook rendering, Github Pages) are available in [https://github.com/mysociety/data_common/blob/main/data-repo-readme.md](Data Common readme file).