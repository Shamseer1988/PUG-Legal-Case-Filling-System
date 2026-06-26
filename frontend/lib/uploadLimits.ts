/** Shared client-side upload caps - mirror the backend's
 *  MAX_UPLOAD_BYTES (50 MB) and a stricter cap for image-only
 *  uploads. Reject oversized files BEFORE the request leaves the
 *  browser so the user doesn't wait through a 50 MB transfer to
 *  learn it was rejected. */

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

function fmt(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Throw a user-friendly Error when ``file`` is larger than ``limit``.
 *  Callers should catch and surface via their existing toast/error UI.
 */
export function assertUploadSize(
  file: File,
  limit: number = MAX_UPLOAD_BYTES,
): void {
  if (file.size > limit) {
    throw new Error(
      `"${file.name}" is ${fmt(file.size)} - that exceeds the ` +
        `${fmt(limit)} upload limit. Please attach a smaller file.`,
    );
  }
}
