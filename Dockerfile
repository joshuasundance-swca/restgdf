FROM python:3.11-slim-bookworm
RUN groupadd -g 1001 appgroup && \
    adduser --uid 1001 --gid 1001 --disabled-password --gecos '' appuser
USER 1001
ENV PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN pip install --user --no-cache-dir --upgrade pip

COPY ./requirements.txt /home/appuser/requirements.txt
RUN pip install --user --no-cache-dir -r /home/appuser/requirements.txt

COPY ./requirements-dev.txt /home/appuser/requirements-dev.txt
RUN pip install --user --no-cache-dir -r /home/appuser/requirements-dev.txt

COPY restgdf /home/appuser/restgdf
WORKDIR /home/appuser/restgdf/
CMD ["/bin/bash"]
