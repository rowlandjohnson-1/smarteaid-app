# Use an official Python runtime as a parent image
# Using python 3.12 based on your preferences
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Prevent python from writing pyc files to disc
# and prevent buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies if needed (e.g., for libraries that require compilation)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install pip requirements
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# Assumes your FastAPI app code is in an 'app' subdirectory within 'backend'
COPY ./app /app/app

# Expose the port the app runs on (uvicorn default is 8000)
EXPOSE 8000

# Command to run the application using uvicorn
# Starts the server on 0.0.0.0 to be accessible from outside the container
# Assumes your FastAPI app instance is named 'app' in 'backend/app/main.py'
# Adjust the path 'app.main:app' if your file/instance name is different
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
