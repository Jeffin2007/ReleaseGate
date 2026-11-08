import { useState, useMemo } from "react";
import {
  GitBranch,
  Plus,
  Trash2,
  Eye,
  CheckCircle,
  XCircle,
  Loader2,
  Shield,
  RotateCcw,
  ChevronRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import type { TransformationOperation, TransformationSpec, TransformationPreview } from "@/lib/transformations";
import { DEMO_DATASETS } from "@/lib/api/mockData";

const MASKING_STRATEGIES = [
  { value: "full_redaction", label: "Full Redaction" },
  { value: "partial_email", label: "Partial Email" },
  { value: "partial_phone", label: "Partial Phone" },
  { value: "last_4_visible", label: "Last 4 Visible" },
  { value: "custom_placeholder", label: "Custom Placeholder" },
];

const GENERALIZATION_STRATEGIES = [
  { value: "numeric_binning", label: "Numeric Binning" },
  { value: "date_truncation", label: "Date Truncation" },
  { value: "category_bucketing", label: "Category Bucketing" },
];

export function TransformationWorkspace() {
  const { isAuthenticated } = useAuth();
  const [operations, setOperations] = useState<TransformationOperation[]>([]);
  const [rationale, setRationale] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [preview, setPreview] = useState<TransformationPreview | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [useDemoData, setUseDemoData] = useState(false);

  const addOperation = (type: string) => {
    const base: TransformationOperation = {
      operation: type as TransformationOperation["operation"],
      column: "",
    };

    if (type === "mask_column") {
      base.strategy = "full_redaction";
      base.placeholder = "[REDACTED]";
    } else if (type === "pseudonymize_column") {
      base.prefix = "PSEUDO_";
    } else if (type === "generalize_column") {
      base.strategy = "numeric_binning";
    } else if (type === "filter_rows") {
      base.operator = "equals";
    }

    setOperations((prev) => [...prev, base]);
  };

  const updateOperation = (index: number, key: string, value: any) => {
    setOperations((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [key]: value };
      return next;
    });
  };

  const removeOperation = (index: number) => {
    setOperations((prev) => prev.filter((_, i) => i !== index));
  };

  const simulatePreview = () => {
    setIsPreviewing(true);
    setTimeout(() => {
      const preview: TransformationPreview = {
        columns_removed: operations.filter((o) => o.operation === "remove_column").map((o) => o.column),
        columns_modified: operations.filter((o) => ["mask_column", "pseudonymize_column", "generalize_column"].includes(o.operation)).map((o) => o.column),
        columns_added: [],
        rows_removed: operations.filter((o) => o.operation === "filter_rows").length * 12,
        input_row_count: 1500,
        output_row_count: 1500 - operations.filter((o) => o.operation === "filter_rows").length * 12,
        estimated_sanitization_level:
          operations.some((o) => o.operation === "remove_column") ? "full" :
          operations.some((o) => o.operation === "mask_column") ? "partial" : "minimal",
        pii_addressed: operations.filter((o) => ["mask_column", "pseudonymize_column"].includes(o.operation)).map((o) => o.column),
      };
      setPreview(preview);
      setIsPreviewing(false);
      setUseDemoData(true);
    }, 800);
  };

  const handleSubmit = async () => {
    if (!rationale || operations.length === 0) return;
    setIsSubmitting(true);
    await new Promise((r) => setTimeout(r, 1500));
    setIsSubmitting(false);
  };

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-rg-text flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-rg-primary" />
            Transformation Workspace
            {useDemoData && (
              <Badge variant="info" className="text-[10px] px-2 py-0">Demo</Badge>
            )}
          </h1>
          <p className="text-sm text-rg-text-muted mt-1">
            Define allowlisted transformation operations to sanitize datasets before release.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={simulatePreview} loading={isPreviewing}>
            <Eye className="h-4 w-4" />
            Simulate Preview
          </Button>
          <Button size="sm" disabled={operations.length === 0 || !rationale} onClick={handleSubmit} loading={isSubmitting}>
            <RotateCcw className="h-4 w-4" />
            Apply Transformation
          </Button>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Operations editor */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-rg-text-muted" />
                Transformation Operations
              </CardTitle>
              <div className="flex gap-2">
                <OperationButton onClick={() => addOperation("remove_column")}>
                  <Trash2 className="h-4 w-4" />
                  Remove Column
                </OperationButton>
                <OperationButton onClick={() => addOperation("mask_column")}>
                  <Eye className="h-4 w-4" />
                  Mask Column
                </OperationButton>
                <OperationButton onClick={() => addOperation("pseudonymize_column")}>
                  <Shield className="h-4 w-4" />
                  Pseudonymize
                </OperationButton>
                <OperationButton onClick={() => addOperation("generalize_column")}>
                  <RotateCcw className="h-4 w-4" />
                  Generalize
                </OperationButton>
                <OperationButton onClick={() => addOperation("filter_rows")}>
                  <Filter className="h-4 w-4" />
                  Filter Rows
                </OperationButton>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {operations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-rg-text-muted">
                  <GitBranch className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm mb-1">No operations defined</p>
                  <p className="text-xs">Add allowlisted operations above to begin</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {operations.map((op, i) => (
                    <OperationRow
                      key={i}
                      operation={op}
                      index={i}
                      total={operations.length}
                      onChange={(key, value) => updateOperation(i, key, value)}
                      onRemove={() => removeOperation(i)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Rationale */}
          <Card className="bg-rg-surface-alt/50 border-rg-border/80">
            <CardContent className="p-5">
              <label className="block text-sm font-medium text-rg-text mb-2">
                Governance Rationale <span className="text-red-500">*</span>
              </label>
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="Explain the governance justification for this transformation (min 5 characters, max 1000)"
                className="w-full flex-1 resize-none rounded-lg border border-rg-border bg-white px-3 py-2 text-sm text-rg-text placeholder:text-rg-text-muted focus:border-rg-primary focus:ring-2 focus:ring-rg-primary/20"
                rows={4}
              />
              <div className="flex justify-between mt-1">
                <p className="text-xs text-rg-text-muted">Required: Explain the governance justification for this transformation.</p>
                <span className={cn("text-xs", rationale.length > 1000 ? "text-red-500" : "text-rg-text-muted")}>
                  {rationale.length}/1000
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Submission result */}
          {isSubmitting && (
            <Card className="border-rg-primary/30 bg-rg-primary/5">
              <CardContent className="p-5 flex items-center gap-3">
                <Loader2 className="h-5 w-5 text-rg-primary animate-spin shrink-0" />
                <div>
                  <p className="text-sm font-medium text-rg-text">Applying transformation…</p>
                  <p className="text-xs text-rg-text-muted">This operation is being processed by the local execution service.</p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Preview panel */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Eye className="h-4 w-4 text-rg-text-muted" />
                Transformation Preview
              </CardTitle>
              <CardDescription>Before-and-after summary</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {isPreviewing ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 text-rg-primary animate-spin" />
                  <p className="text-sm text-rg-text-muted ml-2">Computing preview…</p>
                </div>
              ) : preview ? (
                <div className="space-y-4">
                  {/* Sanitization level */}
                  <div className="flex items-center justify-between p-3 bg-rg-surface-alt rounded-lg">
                    <span className="text-xs text-rg-text-muted uppercase tracking-wider">Sanitization Level</span>
                    <Badge className={
                      preview.estimated_sanitization_level === "full" ? "bg-green-100 text-green-700 border-green-200" :
                      preview.estimated_sanitization_level === "partial" ? "bg-amber-100 text-amber-700 border-amber-200" :
                      "bg-slate-100 text-slate-700 border-slate-200"
                    }>
                      {preview.estimated_sanitization_level.toUpperCase()}
                    </Badge>
                  </div>

                  {/* Row count */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-rg-surface-alt rounded-lg">
                      <p className="text-xs text-rg-text-muted mb-0.5">Input Rows</p>
                      <p className="text-lg font-bold text-rg-text">{preview.input_row_count.toLocaleString()}</p>
                    </div>
                    <div className="p-3 bg-rg-surface-alt rounded-lg">
                      <p className="text-xs text-rg-text-muted mb-0.5">Output Rows</p>
                      <p className="text-lg font-bold text-rg-text">
                        {preview.output_row_count.toLocaleString()}
                        {preview.rows_removed > 0 && (
                          <span className="text-xs text-red-500 ml-1">
                            (-{preview.rows_removed})
                          </span>
                        )}
                      </p>
                    </div>
                  </div>

                  {/* Operations summary */}
                  <div className="space-y-2">
                    <p className="text-xs text-rg-text-muted uppercase tracking-wider">Operations</p>
                    <div className="space-y-1.5">
                      {operations.map((op, i) => (
                        <div key={i} className="flex items-center justify-between text-sm p-2 bg-rg-surface rounded-lg">
                          <div className="flex items-center gap-2 min-w-0">
                            <OperationIcon operation={op.operation} />
                            <span className="text-rg-text truncate">{op.operation.replace(/_/g, " ")}</span>
                            {op.column && (
                              <span className="text-xs text-rg-text-muted font-mono">{op.column}</span>
                            )}
                          </div>
                          <Badge variant="outline" className="text-[10px]">
                            {op.strategy || op.operator || op.operation === "remove_column" ? "remove" : "apply"}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Output summary */}
                  <div className="pt-3 border-t border-rg-border/50 space-y-2">
                    <p className="text-xs text-rg-text-muted uppercase tracking-wider">Expected Changes</p>
                    {preview.columns_removed.length > 0 && (
                      <div className="flex items-center gap-2 text-sm">
                        <Trash2 className="h-4 w-4 text-red-500 shrink-0" />
                        <span className="text-rg-text">
                          Remove: <span className="font-medium">{preview.columns_removed.join(", ")}</span>
                        </span>
                      </div>
                    )}
                    {preview.columns_modified.length > 0 && (
                      <div className="flex items-center gap-2 text-sm">
                        <Eye className="h-4 w-4 text-amber-500 shrink-0" />
                        <span className="text-rg-text">
                          Modify: <span className="font-medium">{preview.columns_modified.join(", ")}</span>
                        </span>
                      </div>
                    )}
                    {preview.pii_addressed.length > 0 && (
                      <div className="flex items-center gap-2 text-sm">
                        <Shield className="h-4 w-4 text-green-500 shrink-0" />
                        <span className="text-rg-text">
                          PII addressed: <span className="font-medium">{preview.pii_addressed.join(", ")}</span>
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Apply button */}
                  <Button className="w-full" size="sm" disabled={isSubmitting} onClick={handleSubmit}>
                    <RotateCcw className="h-4 w-4" />
                    Apply Transformation
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-rg-text-muted">
                  <Eye className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm mb-1">No preview available</p>
                  <p className="text-xs">Add operations and simulate a preview</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Constraints reminder */}
          <Card>
            <CardContent className="p-4">
              <h4 className="text-xs font-semibold text-rg-text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5" />
                Allowlisted Operations
              </h4>
              <ul className="text-xs text-rg-text-muted space-y-1.5">
                <li className="flex items-center gap-1.5">
                  <CheckCircle className="h-3 w-3 text-green-500 shrink-0" />
                  remove_column — Drop non-essential columns
                </li>
                <li className="flex items-center gap-1.5">
                  <Eye className="h-3 w-3 text-amber-500 shrink-0" />
                  mask_column — Redact values (5 strategies)
                </li>
                <li className="flex items-center gap-1.5">
                  <Shield className="h-3 w-3 text-green-500 shrink-0" />
                  pseudonymize_column — Deterministic tokens
                </li>
                <li className="flex items-center gap-1.5">
                  <RotateCcw className="h-3 w-3 text-blue-500 shrink-0" />
                  generalize_column — Coarsen values
                </li>
                <li className="flex items-center gap-1.5">
                  <Filter className="h-3 w-3 text-purple-500 shrink-0" />
                  filter_rows — Declarative row filtering
                </li>
              </ul>
              <p className="text-xs text-rg-text-muted mt-3 border-t border-rg-border/50 pt-3">
                No SQL, shell commands, or arbitrary code execution permitted.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function OperationButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-rg-text-muted bg-rg-surface-alt border border-rg-border rounded-md hover:bg-rg-primary-light hover:text-rg-primary hover:border-rg-primary-light transition-colors"
    >
      {children}
    </button>
  );
}

function OperationRow({
  operation,
  index,
  total,
  onChange,
  onRemove,
}: {
  operation: TransformationOperation;
  index: number;
  total: number;
  onChange: (key: string, value: any) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-start gap-3 p-3 bg-rg-surface rounded-lg border border-rg-border">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-2">
          <OperationIcon operation={operation.operation} />
          <span className="text-sm font-medium text-rg-text capitalize">
            {operation.operation.replace(/_/g, " ")}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="text-xs text-rg-text-muted">Column</label>
            <Input
              value={operation.column}
              onChange={(e) => onChange("column", e.target.value)}
              placeholder="Column name"
              className="h-8 text-xs"
            />
          </div>

          {operation.operation === "mask_column" && (
            <div className="space-y-1">
              <label className="text-xs text-rg-text-muted">Strategy</label>
              <Select
                options={MASKING_STRATEGIES}
                value={operation.strategy || "full_redaction"}
                onChange={(e) => onChange("strategy", e.target.value)}
                className="h-8 text-xs"
              />
            </div>
          )}

          {operation.operation === "pseudonymize_column" && (
            <div className="space-y-1">
              <label className="text-xs text-rg-text-muted">Prefix</label>
              <Input
                value={operation.prefix || "PSEUDO_"}
                onChange={(e) => onChange("prefix", e.target.value)}
                className="h-8 text-xs"
              />
            </div>
          )}

          {operation.operation === "generalize_column" && (
            <div className="space-y-1">
              <label className="text-xs text-rg-text-muted">Strategy</label>
              <Select
                options={GENERALIZATION_STRATEGIES}
                value={operation.strategy || "numeric_binning"}
                onChange={(e) => onChange("strategy", e.target.value)}
                className="h-8 text-xs"
              />
            </div>
          )}

          {operation.operation === "filter_rows" && (
            <div className="space-y-1">
              <label className="text-xs text-rg-text-muted">Operator</label>
              <Select
                options={[
                  { value: "equals", label: "Equals" },
                  { value: "not_equals", label: "Not Equals" },
                  { value: "greater_than", label: "Greater Than" },
                  { value: "less_than", label: "Less Than" },
                  { value: "in_list", label: "In List" },
                  { value: "is_null", label: "Is Null" },
                ]}
                value={operation.operator || "equals"}
                onChange={(e) => onChange("operator", e.target.value)}
                className="h-8 text-xs"
              />
            </div>
          )}
        </div>

        {operation.operation === "mask_column" && operation.strategy === "custom_placeholder" && (
          <div className="col-span-2 space-y-1">
            <label className="text-xs text-rg-text-muted">Placeholder Text</label>
            <Input
              value={operation.placeholder || "[REDACTED]"}
              onChange={(e) => onChange("placeholder", e.target.value)}
              className="h-8 text-xs"
            />
          </div>
        )}
      </div>

      <button
        onClick={onRemove}
        className="mt-1 p-1 text-rg-text-muted hover:text-red-600 hover:bg-red-50 rounded transition-colors shrink-0"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

function OperationIcon({ operation }: { operation: string }) {
  const icons: Record<string, React.ComponentType<{ className?: string }>> = {
    remove_column: Trash2,
    mask_column: Eye,
    pseudonymize_column: Shield,
    generalize_column: RotateCcw,
    filter_rows: Filter,
  };
  const Icon = icons[operation] || Shield;
  return <Icon className="h-4 w-4 text-rg-text-muted shrink-0" />;
}
