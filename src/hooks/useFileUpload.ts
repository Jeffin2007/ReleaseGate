import { useState, useCallback } from "react";
import { api, DatasetSummary } from "@/lib/api";

export function useFileUpload() {
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(
    async (file: File): Promise<DatasetSummary | null> => {
      setIsUploading(true);
      setProgress(0);
      setError(null);

      try {
        const formData = new FormData();
        formData.append("file", file);

        setProgress(30);
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onprogress = (e) => {
            if (e.lengthComputable) {
              setProgress(30 + Math.round((e.loaded / e.total) * 40));
            }
          };
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(new Error("Failed to read file"));
          reader.readAsDataURL(file);
        });

        setProgress(70);
        const bytes = atob(base64.split(",")[1]);
        const uint8 = new Uint8Array(bytes.length);
        for (let i = 0; i < bytes.length; i++) {
          uint8[i] = bytes.charCodeAt(i);
        }

        const datasetName = file.name.replace(/\.[^.]+$/, "");
        const payload = await api.registerMetadata({
          dataset_name: datasetName,
          description: `Imported ${file.name}`,
          content_hash: "",
          file_format: file.name.split(".").pop() || "csv",
          file_size: file.size,
          local_artifact_ref: "",
          profile: {
            row_count: 0,
            column_count: 0,
            columns: [],
            column_types: {},
            null_counts: {},
            null_percentages: {},
            duplicate_row_count: 0,
            file_format: file.name.split(".").pop() || "csv",
          },
        });

        setProgress(100);
        return payload;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
        return null;
      } finally {
        setTimeout(() => setIsUploading(false), 500);
      }
    },
    []
  );

  return { isUploading, progress, error, upload };
}
