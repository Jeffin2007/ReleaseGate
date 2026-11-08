// Transformation operation types for ReleaseGate
export type OperationType =
  | "remove_column"
  | "mask_column"
  | "pseudonymize_column"
  | "generalize_column"
  | "filter_rows";

export type MaskingStrategy =
  | "full_redaction"
  | "partial_email"
  | "partial_phone"
  | "last_4_visible"
  | "custom_placeholder";

export type GeneralizationStrategy =
  | "numeric_binning"
  | "date_truncation"
  | "category_bucketing";

export type FilterOperator =
  | "equals"
  | "not_equals"
  | "greater_than"
  | "greater_than_or_equal"
  | "less_than"
  | "less_than_or_equal"
  | "in_list"
  | "not_in_list"
  | "is_null"
  | "is_not_null";

export interface TransformationOperation {
  operation: OperationType;
  column: string;
  strategy?: MaskingStrategy | GeneralizationStrategy;
  placeholder?: string;
  prefix?: string;
  bins?: number[];
  bin_labels?: string[];
  date_interval?: "YEAR" | "MONTH" | "DECADE";
  category_mapping?: Record<string, string>;
  operator?: FilterOperator;
  value?: string | number | boolean;
  values_list?: (string | number | boolean)[];
}

export interface TransformationSpec {
  operations: TransformationOperation[];
  rationale: string;
}

export interface TransformationPreview {
  columns_removed: string[];
  columns_modified: string[];
  columns_added: string[];
  rows_removed: number;
  input_row_count: number;
  output_row_count: number;
  estimated_sanitization_level: "full" | "partial" | "minimal";
  pii_addressed: string[];
}

export interface TransformationResult {
  proposal_id: string;
  dataset_id: string;
  base_version: number;
  target_version: number;
  rationale: string;
  operations_count: number;
  preview: TransformationPreview;
  simulated_output_hash: string;
  status: "PROPOSED" | "APPLIED" | "REJECTED";
}
