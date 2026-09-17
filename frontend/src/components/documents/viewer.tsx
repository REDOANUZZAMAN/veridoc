"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft, ChevronRight, Download, Layers, Maximize2, Minimize2, RotateCw, Ruler,
  ZoomIn, ZoomOut,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { InfoTip } from "@/components/ui/tooltip";
import { documentFileUrl, pageRenderUrl } from "@/lib/client";
import { severityTone } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DocumentPage, Finding, Region } from "@/lib/types";

const ZOOM_STEPS = [0.25, 0.4, 0.5, 0.65, 0.8, 1, 1.25, 1.5, 2, 3];

export interface ViewerRegion {
  id: string;
  page: number;
  region: Region;
  label: string;
  severity: string;
  kind: string;
}

/** Findings that can be drawn on the page, in a stable order. */
export function regionsFromFindings(findings: Finding[]): ViewerRegion[] {
  return findings
    .filter((finding) => finding.region && finding.page)
    .map((finding) => ({
      id: finding.finding_id,
      page: finding.page!,
      region: finding.region!,
      label: finding.title,
      severity: finding.severity,
      kind: finding.kind,
    }));
}

export function DocumentViewer({
  documentId,
  documentRef,
  filename,
  pages,
  regions,
  activeId,
  onSelect,
  canDownload,
}: {
  documentId: string;
  documentRef: string;
  filename: string;
  pages: DocumentPage[];
  regions: ViewerRegion[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  canDownload: boolean;
}) {
  const [pageNumber, setPageNumber] = useState(pages[0]?.page_number ?? 1);
  // Fit-to-width by default: an A4 page rendered at 150 DPI is 1275px wide, which
  // no split-screen pane can show at 1:1. "Fit" is what an investigator wants on
  // open; explicit zoom is for reading a region closely.
  const [zoom, setZoom] = useState<number | null>(null);
  const [fitScale, setFitScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [layer, setLayer] = useState<string>("page");
  const [showRegions, setShowRegions] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  const page = pages.find((item) => item.page_number === pageNumber) ?? pages[0];
  const pageRegions = useMemo(
    () => regions.filter((region) => region.page === pageNumber),
    [regions, pageNumber],
  );
  const availableLayers = useMemo(
    () => ["page", ...(page?.layers ?? []).filter((item) => item !== "thumbnail")],
    [page],
  );

  // Selecting a finding on another page moves the viewer to that page.
  useEffect(() => {
    if (!activeId) return;
    const target = regions.find((region) => region.id === activeId);
    if (target && target.page !== pageNumber) setPageNumber(target.page);
  }, [activeId, regions, pageNumber]);

  useEffect(() => {
    if (!availableLayers.includes(layer)) setLayer("page");
  }, [availableLayers, layer]);

  // Track the pane width so "fit" survives window resizing and the sidebar
  // collapsing on smaller screens.
  useEffect(() => {
    const element = viewportRef.current;
    const width = page?.width;
    if (!element || !width) return;
    const measure = () => {
      const available = element.clientWidth - 32;
      setFitScale(Math.max(0.1, Math.min(2, available / width)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [page?.width, fullscreen]);

  if (!page) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border bg-muted/30 p-10 text-center">
        <p className="max-w-xs text-xs text-muted-foreground">
          No page renders are available. The original file is preserved and can be reprocessed from
          the Overview tab.
        </p>
      </div>
    );
  }

  const effectiveZoom = zoom ?? fitScale;
  const rotated = rotation === 90 || rotation === 270;
  const zoomIndex = ZOOM_STEPS.findIndex((step) => step >= effectiveZoom - 0.001);

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-lg border bg-card",
        fullscreen && "fixed inset-3 z-50 shadow-2xl",
      )}
    >
      <header className="flex flex-wrap items-center gap-1.5 border-b px-2.5 py-2">
        <div className="mr-1 flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
            aria-label="Previous page"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="tabular min-w-[62px] text-center text-2xs text-muted-foreground">
            {pageNumber} / {pages.length}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={pageNumber >= pages.length}
            onClick={() => setPageNumber((current) => Math.min(pages.length, current + 1))}
            aria-label="Next page"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={effectiveZoom <= ZOOM_STEPS[0]}
            onClick={() =>
              setZoom(ZOOM_STEPS[Math.max(0, (zoomIndex <= 0 ? 1 : zoomIndex) - 1)])
            }
            aria-label="Zoom out"
          >
            <ZoomOut className="size-4" />
          </Button>
          <button
            type="button"
            onClick={() => setZoom(zoom === null ? 1 : null)}
            className="tabular min-w-[58px] rounded px-1 text-2xs text-muted-foreground hover:bg-accent"
            title={zoom === null ? "Switch to 100%" : "Fit to width"}
          >
            {zoom === null ? "Fit" : `${Math.round(effectiveZoom * 100)}%`}
          </button>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={effectiveZoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}
            onClick={() =>
              setZoom(
                ZOOM_STEPS[
                  Math.min(ZOOM_STEPS.length - 1, zoomIndex < 0 ? ZOOM_STEPS.length - 1 : zoomIndex + 1)
                ],
              )
            }
            aria-label="Zoom in"
          >
            <ZoomIn className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setRotation((current) => (current + 90) % 360)}
            aria-label="Rotate 90 degrees"
          >
            <RotateCw className="size-4" />
          </Button>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-1.5 text-2xs">
              <Layers className="size-3.5" />
              {layer === "page" ? "Page" : layer.toUpperCase()}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-60">
            <DropdownMenuLabel>Rendered layer</DropdownMenuLabel>
            {availableLayers.map((item) => (
              <DropdownMenuCheckboxItem
                key={item}
                checked={layer === item}
                onCheckedChange={() => setLayer(item)}
              >
                {item === "page" ? "Document render" : `${item.toUpperCase()} forensic layer`}
              </DropdownMenuCheckboxItem>
            ))}
            {availableLayers.length === 1 && (
              <p className="px-2 py-1.5 text-2xs text-muted-foreground">
                No forensic raster layer was produced for this page. Pixel-history layers are only
                generated where they carry information.
              </p>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuCheckboxItem
              checked={showRegions}
              onCheckedChange={(value) => setShowRegions(Boolean(value))}
            >
              Show highlighted regions ({pageRegions.length})
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="ml-auto flex items-center gap-1">
          <InfoTip
            label={`Render ${page.width}×${page.height}px at ${page.render_dpi} DPI. ${
              page.has_text_layer
                ? "This page has an embedded text layer, so field coordinates are exact."
                : "This page has no text layer; values were read by pixel OCR."
            }`}
          >
            <Badge variant="muted" className="cursor-help">
              <Ruler className="size-3" />
              {page.has_text_layer ? "Text layer" : "Scanned"}
            </Badge>
          </InfoTip>

          {canDownload && (
            <Button variant="ghost" size="icon-sm" asChild aria-label="Download original">
              <a href={documentFileUrl(documentId, "attachment")} download={filename}>
                <Download className="size-4" />
              </a>
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setFullscreen((current) => !current)}
            aria-label={fullscreen ? "Exit full screen" : "Full screen"}
          >
            {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </Button>
        </div>
      </header>

      <div
        ref={viewportRef}
        className={cn(
          "min-h-0 flex-1 overflow-auto bg-[#eef1f5] p-4 scrollbar-thin dark:bg-[#0e1219]",
          fullscreen ? "" : "max-h-[calc(100vh-15rem)]",
        )}
      >
        {/* The outer box carries the *scaled* layout size and the inner box keeps
            the page's own pixel coordinate space, so region highlights can be
            positioned in render pixels while the page is scaled to fit. */}
        <div
          className="mx-auto"
          style={{
            width: rotated ? page.height * effectiveZoom : page.width * effectiveZoom,
            height: rotated ? page.width * effectiveZoom : page.height * effectiveZoom,
          }}
        >
          <div
            className="relative shadow-lg ring-1 ring-black/10"
            style={{
              width: page.width,
              height: page.height,
              transform: `translate(${rotated ? page.height * effectiveZoom : 0}px, 0px) scale(${effectiveZoom}) rotate(${rotation}deg)`,
              transformOrigin: "top left",
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={pageRenderUrl(documentId, page.page_number, layer)}
              alt={`${documentRef} page ${page.page_number}${layer === "page" ? "" : ` (${layer} layer)`}`}
              width={page.width}
              height={page.height}
              className="block h-full w-full select-none bg-white"
              draggable={false}
            />

            {showRegions &&
              pageRegions.map((region) => {
                const tone = severityTone(region.severity);
                const active = activeId === region.id;
                return (
                  <button
                    key={region.id}
                    type="button"
                    data-active={active}
                    onClick={() => onSelect(active ? null : region.id)}
                    title={region.label}
                    className={cn(
                      "evidence-region",
                      tone.border,
                      active ? "bg-primary/15" : "bg-transparent hover:bg-primary/10",
                    )}
                    style={{
                      left: `${(region.region.x / page.width) * 100}%`,
                      top: `${(region.region.y / page.height) * 100}%`,
                      width: `${(region.region.width / page.width) * 100}%`,
                      height: `${(region.region.height / page.height) * 100}%`,
                      borderColor: active ? "hsl(var(--ring))" : undefined,
                    }}
                  >
                    <span className="sr-only">{region.label}</span>
                  </button>
                );
              })}
          </div>
        </div>
      </div>

      <footer className="flex items-center justify-between gap-2 border-t px-3 py-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-2xs text-muted-foreground">{filename}</span>
        </div>
        <span className="shrink-0 text-2xs text-muted-foreground">
          {pageRegions.length
            ? `${pageRegions.length} highlighted region${pageRegions.length === 1 ? "" : "s"} on this page`
            : "No highlighted regions on this page"}
        </span>
      </footer>
    </div>
  );
}

/** Page strip for multi-page documents. */
export function PageStrip({
  documentId,
  pages,
  pageNumber,
  onSelect,
}: {
  documentId: string;
  pages: DocumentPage[];
  pageNumber: number;
  onSelect: (page: number) => void;
}) {
  if (pages.length < 2) return null;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
      {pages.map((page) => (
        <button
          key={page.page_number}
          type="button"
          onClick={() => onSelect(page.page_number)}
          className={cn(
            "shrink-0 overflow-hidden rounded border-2 transition-colors",
            page.page_number === pageNumber ? "border-primary" : "border-transparent hover:border-border",
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={pageRenderUrl(documentId, page.page_number, "thumbnail")}
            alt={`Page ${page.page_number}`}
            className="h-20 w-auto bg-white"
          />
          <span className="block bg-card px-1 py-0.5 text-center text-2xs text-muted-foreground">
            {page.page_number}
          </span>
        </button>
      ))}
    </div>
  );
}
