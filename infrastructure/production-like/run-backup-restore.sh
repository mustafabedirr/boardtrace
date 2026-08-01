#!/bin/sh
set -eu

mkdir -p /work
rm -f /work/*

pg_dump --format=custom --file=/work/boardtrace.dump "$SOURCE_DATABASE_URL"
age-keygen -o /work/age-key.txt 2>/work/age-keygen.log
recipient="$(age-keygen -y /work/age-key.txt)"
age --recipient "$recipient" --output /work/boardtrace.dump.age /work/boardtrace.dump
checksum="$(sha256sum /work/boardtrace.dump.age | cut -d ' ' -f 1)"
size="$(wc -c < /work/boardtrace.dump.age | tr -d ' ')"

aws --endpoint-url "$S3_ENDPOINT" s3api create-bucket --bucket "$S3_BUCKET"
aws --endpoint-url "$S3_ENDPOINT" s3 cp /work/boardtrace.dump.age \
  "s3://$S3_BUCKET/boardtrace.dump.age" --metadata "sha256=$checksum"

remote_size="$(aws --endpoint-url "$S3_ENDPOINT" s3api head-object \
  --bucket "$S3_BUCKET" --key boardtrace.dump.age --query ContentLength --output text)"
remote_checksum="$(aws --endpoint-url "$S3_ENDPOINT" s3api head-object \
  --bucket "$S3_BUCKET" --key boardtrace.dump.age --query Metadata.sha256 --output text)"
test "$remote_size" = "$size"
test "$remote_checksum" = "$checksum"

aws --endpoint-url "$S3_ENDPOINT" s3 cp \
  "s3://$S3_BUCKET/boardtrace.dump.age" /work/downloaded.dump.age
test "$(sha256sum /work/downloaded.dump.age | cut -d ' ' -f 1)" = "$checksum"
age --decrypt --identity /work/age-key.txt \
  --output /work/restored.dump /work/downloaded.dump.age
pg_restore --dbname="$RESTORE_DATABASE_URL" --exit-on-error --no-owner /work/restored.dump
test "$(psql "$RESTORE_DATABASE_URL" -Atc 'select count(*) from alembic_version')" = "1"

rm -f /work/boardtrace.dump /work/restored.dump /work/downloaded.dump.age /work/age-key.txt
echo "encrypted backup upload and isolated restore validation passed"
