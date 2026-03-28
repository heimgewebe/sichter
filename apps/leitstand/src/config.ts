export const envConfig = {
  port: Number(process.env.LEITSTAND_PORT ?? process.env.PORT ?? 3000),
  host: process.env.LEITSTAND_HOST ?? '127.0.0.1',
  strictMode: process.env.LEITSTAND_STRICT === '1',
  artifactDir: process.env.LEITSTAND_ARTIFACT_DIR ?? '',
  chronikDir: process.env.LEITSTAND_CHRONIK_DIR ?? '',
} as const;
