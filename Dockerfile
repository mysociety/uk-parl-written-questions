FROM ghcr.io/mysociety/data_common:sha-118ef66

# Make an empty project directory so the 'self' setup doesn't fail and scripts can be setup
# Override the .pth created at previous stages to point to where the working directory will land
COPY pyproject.toml poetry.loc[k] /setup/ 
COPY src/data_common/pyproject.toml src/data_common/poetry.loc[k] /setup/src/data_common/
ENV WORKSPACE_NAME uk_parl_written_questions
RUN mkdir /setup/src/$WORKSPACE_NAME \
    && touch /setup/src/$WORKSPACE_NAME/__init__.py \
    && mkdir --parents /setup/src/data_common/src/data_common \
    && touch /setup/src/data_common/src/data_common/__init__.py \
    && export PATH="/root/.local/bin:$PATH" \
    && cd /setup/ && poetry install \
    && echo "/workspaces/$WORKSPACE_NAME/src/" > /usr/local/lib/python3.10/site-packages/$WORKSPACE_NAME.pth \
    && echo "/workspaces/$WORKSPACE_NAME/src/data_common/src" > /usr/local/lib/python3.10/site-packages/data_common.pth
