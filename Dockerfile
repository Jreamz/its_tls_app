# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory to /app
WORKDIR /app

# Copy the pyproject.toml and poetry.lock file to the container
COPY pyproject.toml poetry.lock /app/

# Install Poetry and project dependencies
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-root --no-dev

# Copy the rest of your project code to the container
COPY . /app/

# Run your FastAPI application
CMD ["poetry", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
