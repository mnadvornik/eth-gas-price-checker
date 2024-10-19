# Use an official Python runtime as a base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make sure the /data directory exists for mounting
RUN mkdir -p /data

# Run gas_price_checker.py when the container launches
CMD ["python", "gas_price_checker.py"]
