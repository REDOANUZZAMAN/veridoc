"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import {
  AlertTriangle, CheckCircle2, FileUp, Loader2, ShieldCheck, Upload, X,
} from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

const ACCEPTED = ".pdf,.jpg,.jpeg,.png,.tif,.tiff";
const ACCEPTED_MIME = ["application/pdf", "image/jpeg", "image/png", "image/tiff"];

interface Outcome {
  documentId: string;
  documentRef: string;
  filename: string;
  warnings: string[];
  message: string;
  pages: number;
  sha256: string;
}

/**
 * Upload with real progress.
 *
 * XMLHttpRequest rather than fetch because upload progress events are the honest
 * signal here: a 12 MB scan over a slow link takes long enough that a spinner
 * with no position is worse than no feedback at all.
 */
export function UploadDialog({
  claims,
  defaultClaimId,
  trigger,
}: {
  claims: Array<{ id: string; claim_number: string; customer_name: string }>;
  defaultClaimId?: string;
  trigger?: React.ReactNode;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [claimId, setClaimId] = useState(defaultClaimId ?? "");
  const [source, setSource] = useState("portal_upload");
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [errors, setErrors] = useState<Array<{ filename: string; message: string }>>([]);
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
    const accepted: File[] = [];
    const rejected: Array<{ filename: string; message: string }> = [];
    for (const file of Array.from(incoming)) {
      const extensionOk = /\.(pdf|jpe?g|png|tiff?)$/i.test(file.name);
      if (!extensionOk && !ACCEPTED_MIME.includes(file.type)) {
        rejected.push({
          filename: file.name,
          message: "Only PDF, JPG/JPEG, PNG and TIFF documents can be analysed.",
        });
        continue;
      }
      accepted.push(file);
    }
    setFiles((current) => [...current, ...accepted]);
    if (rejected.length) setErrors((current) => [...current, ...rejected]);
  }, []);

  function reset() {
    setFiles([]);
    setProgress({});
    setOutcomes([]);
    setErrors([]);
    setBusy(false);
  }

  function uploadOne(file: File): Promise<void> {
    return new Promise((resolve) => {
      const form = new FormData();
      form.append("file", file);
      if (claimId) form.append("claim_id", claimId);
      form.append("source", source);
      form.append("analyze", "true");

      const request = new XMLHttpRequest();
      request.open("POST", "/api/be/documents");
      request.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          setProgress((current) => ({
            ...current,
            [file.name]: Math.round((event.loaded / event.total) * 100),
          }));
        }
      });
      request.addEventListener("load", () => {
        try {
          const body = JSON.parse(request.responseText);
          if (request.status >= 200 && request.status < 300) {
            setOutcomes((current) => [
              ...current,
              {
                documentId: body.document.id,
                documentRef: body.document.document_ref,
                filename: file.name,
                warnings: body.warnings ?? [],
                message: body.message,
                pages: body.document.page_count,
                sha256: body.document.sha256,
              },
            ]);
            setProgress((current) => ({ ...current, [file.name]: 100 }));
          } else {
            setErrors((current) => [
              ...current,
              { filename: file.name, message: body?.error?.message ?? "Upload rejected." },
            ]);
          }
        } catch {
          setErrors((current) => [
            ...current,
            { filename: file.name, message: "Unexpected response from the service." },
          ]);
        }
        resolve();
      });
      request.addEventListener("error", () => {
        setErrors((current) => [
          ...current,
          { filename: file.name, message: "Network error during upload." },
        ]);
        resolve();
      });
      request.send(form);
    });
  }

  async function startUpload() {
    if (!files.length) return;
    setBusy(true);
    setErrors([]);
    for (const file of files) {
      await uploadOne(file);
    }
    setBusy(false);
    setFiles([]);
    router.refresh();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        {trigger ?? (
          <Button size="sm">
            <Upload className="size-4" /> Upload document
          </Button>
        )}
      </DialogTrigger>

      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Secure document upload</DialogTitle>
          <DialogDescription>
            Content type is verified before anything is stored, a SHA-256 hash is taken at ingest,
            and the original file is never modified or overwritten. Accepted: PDF, JPG/JPEG, PNG,
            TIFF · maximum 25 MB · up to 60 pages.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="claim">Attach to claim</Label>
            <Select value={claimId} onValueChange={setClaimId}>
              <SelectTrigger id="claim">
                <SelectValue placeholder="Unattached (analyse standalone)" />
              </SelectTrigger>
              <SelectContent>
                {claims.map((claim) => (
                  <SelectItem key={claim.id} value={claim.id}>
                    {claim.claim_number} · {claim.customer_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-2xs text-muted-foreground">
              Cross-document comparison only runs for documents in the same claim.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="source">Intake source</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger id="source">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="portal_upload">Customer portal</SelectItem>
                <SelectItem value="agent_upload">Agent / broker</SelectItem>
                <SelectItem value="email_intake">Email intake</SelectItem>
                <SelectItem value="partner_api">Partner API</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-2xs text-muted-foreground">Recorded on the document and in the audit trail.</p>
          </div>
        </div>

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            addFiles(event.dataTransfer.files);
          }}
          className={cn(
            "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging ? "border-primary bg-primary/5" : "border-border bg-muted/30",
          )}
        >
          <FileUp className="size-6 text-muted-foreground" />
          <p className="text-xs font-medium">Drop files here, or</p>
          <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
            Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            className="hidden"
            onChange={(event) => addFiles(event.target.files)}
          />
        </div>

        {files.length > 0 && (
          <ul className="space-y-2">
            {files.map((file) => (
              <li key={file.name} className="rounded-md border p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium">{file.name}</p>
                    <p className="text-2xs text-muted-foreground">
                      {formatBytes(file.size)} · {file.type || "type detected at ingest"}
                    </p>
                  </div>
                  {!busy && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setFiles((current) => current.filter((f) => f !== file))}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X className="size-3.5" />
                    </Button>
                  )}
                </div>
                {progress[file.name] !== undefined && (
                  <Progress value={progress[file.name]} className="mt-2" />
                )}
              </li>
            ))}
          </ul>
        )}

        {errors.map((error, index) => (
          <Alert key={index} variant="danger">
            <AlertTriangle />
            <div>
              <p className="font-semibold">{error.filename}</p>
              <AlertDescription className="text-foreground">{error.message}</AlertDescription>
            </div>
          </Alert>
        ))}

        {outcomes.length > 0 && (
          <div className="space-y-2">
            {outcomes.map((outcome) => (
              <div key={outcome.documentId} className="rounded-md border border-risk-low/30 bg-risk-low/5 p-3">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-risk-low" />
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-xs font-medium">
                      {outcome.documentRef} · {outcome.filename}
                    </p>
                    <p className="text-2xs text-muted-foreground">{outcome.message}</p>
                    <p className="font-mono text-2xs text-muted-foreground">
                      sha256 {outcome.sha256.slice(0, 24)}… · {outcome.pages} page
                      {outcome.pages === 1 ? "" : "s"}
                    </p>
                    {outcome.warnings.map((warning, index) => (
                      <p key={index} className="flex gap-1.5 text-2xs text-risk-review">
                        <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                        {warning}
                      </p>
                    ))}
                    <Button
                      variant="link"
                      size="xs"
                      className="h-auto p-0"
                      onClick={() => {
                        setOpen(false);
                        router.push(`/documents/${outcome.documentId}`);
                      }}
                    >
                      Open investigation →
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <div className="mr-auto flex items-center gap-1.5 text-2xs text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            Files are scanned for active content before analysis begins.
          </div>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            {outcomes.length ? "Done" : "Cancel"}
          </Button>
          <Button onClick={startUpload} disabled={busy || files.length === 0}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
            {busy ? "Uploading…" : `Upload ${files.length || ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
