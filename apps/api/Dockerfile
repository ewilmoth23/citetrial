FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN addgroup --system citetrail && adduser --system --ingroup citetrail --home /nonexistent citetrail
COPY requirements.lock ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN python -m pip install --require-hashes -r requirements.lock
# perl-base is an essential Debian package, but it is not part of CiteTrail's
# runtime. Removing it after every install step eliminates an otherwise
# unfixed high/critical base-image attack surface from the immutable image.
RUN dpkg --purge --force-remove-essential --force-depends perl-base && test ! -e /usr/bin/perl
RUN mkdir -p /data && chown -R citetrail:citetrail /data /app
USER citetrail
ENV CITETRAIL_DATA_DIR=/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
