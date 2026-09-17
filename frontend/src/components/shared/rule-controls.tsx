"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { apiPatch, apiPut } from "@/lib/client";

/** Admin controls that write straight through to the engine's configuration. */
export function RuleToggle({ code, enabled }: { code: string; enabled: boolean }) {
  const router = useRouter();
  const [value, setValue] = useState(enabled);
  const [busy, setBusy] = useState(false);

  return (
    <Switch
      checked={value}
      disabled={busy}
      aria-label={`Enable ${code}`}
      onCheckedChange={async (next) => {
        setValue(next);
        setBusy(true);
        try {
          await apiPatch(`/rules/${code}`, { enabled: next });
          toast.success(next ? `${code} enabled` : `${code} disabled`, {
            description: "Takes effect on the next analysis run.",
          });
          router.refresh();
        } catch (error) {
          setValue(!next);
          toast.error(error instanceof Error ? error.message : "Could not update the rule");
        } finally {
          setBusy(false);
        }
      }}
    />
  );
}

export function RuleWeightInput({ code, weight }: { code: string; weight: number }) {
  const [value, setValue] = useState(String(weight));
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function commit() {
    const parsed = Number(value);
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 60) {
      toast.error("Weight must be between 0 and 60");
      setValue(String(weight));
      return;
    }
    if (parsed === weight) return;
    setBusy(true);
    try {
      await apiPatch(`/rules/${code}`, { weight: parsed });
      toast.success(`${code} weight set to ${parsed}`);
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the weight");
      setValue(String(weight));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Input
      value={value}
      disabled={busy}
      onChange={(event) => setValue(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => event.key === "Enter" && commit()}
      className="tabular h-7 w-16 text-2xs"
      aria-label={`Risk weight for ${code}`}
    />
  );
}

export function RuleSeveritySelect({ code, severity }: { code: string; severity: string }) {
  const [value, setValue] = useState(severity);
  const router = useRouter();

  return (
    <Select
      value={value}
      onValueChange={async (next) => {
        setValue(next);
        try {
          await apiPatch(`/rules/${code}`, { default_severity: next });
          toast.success(`${code} severity set to ${next}`);
          router.refresh();
        } catch (error) {
          setValue(severity);
          toast.error(error instanceof Error ? error.message : "Could not update the severity");
        }
      }}
    >
      <SelectTrigger className="h-7 w-[104px] text-2xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {["info", "low", "medium", "high", "critical"].map((option) => (
          <SelectItem key={option} value={option}>
            {option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ProviderActivateSwitch({
  kind,
  providerKey,
  isActive,
  disabled,
  disabledReason,
}: {
  kind: string;
  providerKey: string;
  isActive: boolean;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  return (
    <Switch
      checked={isActive}
      disabled={busy || disabled || isActive}
      aria-label={`Activate ${providerKey}`}
      title={disabled ? disabledReason : undefined}
      onCheckedChange={async () => {
        setBusy(true);
        try {
          await apiPatch(`/providers/${kind}/${providerKey}`, { is_active: true });
          toast.success(`${providerKey} is now the active ${kind} provider`, {
            description: "Applies to analysis runs started after this change.",
          });
          router.refresh();
        } catch (error) {
          toast.error(error instanceof Error ? error.message : "Could not switch provider");
        } finally {
          setBusy(false);
        }
      }}
    />
  );
}

export function ThresholdEditor({
  review,
  high,
}: {
  review: number;
  high: number;
}) {
  const router = useRouter();
  const [values, setValues] = useState({ review: String(review), high: String(high) });
  const [busy, setBusy] = useState(false);

  async function save() {
    const reviewValue = Number(values.review);
    const highValue = Number(values.high);
    if (!(reviewValue > 0 && reviewValue < highValue && highValue <= 100)) {
      toast.error("Thresholds must satisfy 0 < review < high ≤ 100");
      return;
    }
    setBusy(true);
    try {
      await apiPut("/settings/risk_thresholds", {
        value: { review_recommended: reviewValue, high_concern: highValue },
      });
      toast.success("Risk thresholds updated", {
        description: "Bands are recalculated the next time a document is assessed.",
      });
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the thresholds");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="space-y-1">
        <span className="block text-2xs text-muted-foreground">Review Recommended at</span>
        <Input
          value={values.review}
          onChange={(event) => setValues((current) => ({ ...current, review: event.target.value }))}
          className="tabular h-8 w-20 text-xs"
        />
      </label>
      <label className="space-y-1">
        <span className="block text-2xs text-muted-foreground">High Concern at</span>
        <Input
          value={values.high}
          onChange={(event) => setValues((current) => ({ ...current, high: event.target.value }))}
          className="tabular h-8 w-20 text-xs"
        />
      </label>
      <button
        type="button"
        onClick={save}
        disabled={busy}
        className="h-8 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Save thresholds"}
      </button>
    </div>
  );
}
