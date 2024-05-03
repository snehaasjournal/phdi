import { S3Client, S3ClientConfig } from "@aws-sdk/client-s3";

const config: S3ClientConfig | undefined = process.env.S3_URL
  ? {
      endpoint: process.env.S3_URL,
      forcePathStyle: true,
    }
  : undefined;
export const s3Client = new S3Client({
  region: process.env.AWS_REGION,
  ...config,
});
