/**
 * CARDEX Terminal — Drawing tools taxonomy
 * Source of truth: .cardex-spec/tools.json (95 tools, 13 groups)
 *
 * Geometry normalization notes:
 * - All geometry values in the spec map 1-to-1 to the Geometry union below.
 *   No out-of-union values were found; no normalization was required.
 * - clicks === -1 in the spec (brushes, pointN shapes) is preserved verbatim;
 *   requiredClicks() converts it to -1 (indefinite) per contract.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Geometry =
  | 'placed'   // cursor/toggle mode — no spatial anchor
  | 'point1'   // single anchor
  | 'point2'   // two anchors (segment, arrow, rect bounding box…)
  | 'point3'   // three anchors (channel, rotated rect, arc…)
  | 'channel'  // parallel channel variant (2 line anchors + 1 width anchor)
  | 'fib'      // fibonacci/gann fib family
  | 'gann'     // gann box/square/fan family
  | 'pattern'  // harmonic / Elliott pattern (variable N anchors, fixed per tool)
  | 'range'    // rectangular range selection / projection box
  | 'brush'    // freehand stroke — press-drag-release
  | 'pointN'   // open-ended vertex list, terminated with double-click or Esc
  | 'text'     // text placement (single click, opens editor)
  | 'measure'  // transient measurement overlay

export interface ToolDef {
  id: string
  label: string
  group: string
  geometry: Geometry
  /** Number of clicks to complete placement. -1 = indefinite (brush / pointN). */
  clicks: number
  note: string
}

export interface ToolGroup {
  id: string
  label: string
  tools: ToolDef[]
}

// ---------------------------------------------------------------------------
// Tool groups — VERBATIM from spec, order preserved
// ---------------------------------------------------------------------------

export const TOOL_GROUPS: ToolGroup[] = [
  {
    id: 'cursors',
    label: 'Cursors',
    tools: [
      {
        id: 'cross',
        label: 'Cross',
        group: 'cursors',
        geometry: 'placed',
        clicks: 0,
        note: 'default crosshair cursor, no drawing',
      },
      {
        id: 'dot',
        label: 'Dot',
        group: 'cursors',
        geometry: 'placed',
        clicks: 0,
        note: 'dot pointer cursor mode',
      },
      {
        id: 'arrow',
        label: 'Arrow',
        group: 'cursors',
        geometry: 'placed',
        clicks: 0,
        note: 'standard arrow pointer cursor',
      },
      {
        id: 'eraser',
        label: 'Eraser',
        group: 'cursors',
        geometry: 'placed',
        clicks: 1,
        note: 'click a drawing to delete it',
      },
    ],
  },
  {
    id: 'trend_lines',
    label: 'Trend lines',
    tools: [
      {
        id: 'trend_line',
        label: 'Trend Line',
        group: 'trend_lines',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors define a finite segment',
      },
      {
        id: 'ray',
        label: 'Ray',
        group: 'trend_lines',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors, extends infinitely past second point',
      },
      {
        id: 'info_line',
        label: 'Info Line',
        group: 'trend_lines',
        geometry: 'point2',
        clicks: 2,
        note: 'trend line displaying price/bar/angle delta labels',
      },
      {
        id: 'extended_line',
        label: 'Extended Line',
        group: 'trend_lines',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors, extends infinitely both directions',
      },
      {
        id: 'trend_angle',
        label: 'Trend Angle',
        group: 'trend_lines',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors plus angle readout from horizontal',
      },
      {
        id: 'horizontal_line',
        label: 'Horizontal Line',
        group: 'trend_lines',
        geometry: 'point1',
        clicks: 1,
        note: 'single click sets price level spanning full width',
      },
      {
        id: 'horizontal_ray',
        label: 'Horizontal Ray',
        group: 'trend_lines',
        geometry: 'point1',
        clicks: 1,
        note: 'single anchor extends horizontally to the right',
      },
      {
        id: 'vertical_line',
        label: 'Vertical Line',
        group: 'trend_lines',
        geometry: 'point1',
        clicks: 1,
        note: 'single click sets a time/bar vertical marker',
      },
      {
        id: 'cross_line',
        label: 'Cross Line',
        group: 'trend_lines',
        geometry: 'point1',
        clicks: 1,
        note: 'single click places intersecting horizontal+vertical lines',
      },
      {
        id: 'parallel_channel',
        label: 'Parallel Channel',
        group: 'trend_lines',
        geometry: 'channel',
        clicks: 3,
        note: 'two anchors set the line, third sets channel width',
      },
      {
        id: 'regression_trend',
        label: 'Regression Trend',
        group: 'trend_lines',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors define range, fits linear regression with deviation bands',
      },
      {
        id: 'flat_top_bottom',
        label: 'Flat Top/Bottom',
        group: 'trend_lines',
        geometry: 'channel',
        clicks: 3,
        note: 'two anchors plus third to form horizontal-bounded channel',
      },
      {
        id: 'disjoint_channel',
        label: 'Disjoint Channel',
        group: 'trend_lines',
        geometry: 'channel',
        clicks: 3,
        note: 'three anchors define independent parallel-line channel',
      },
    ],
  },
  {
    id: 'gann_fibonacci',
    label: 'Gann & Fibonacci',
    tools: [
      {
        id: 'fib_retracement',
        label: 'Fib Retracement',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 2,
        note: 'two anchors define swing, draws horizontal retracement levels',
      },
      {
        id: 'trend_based_fib_extension',
        label: 'Trend-Based Fib Extension',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 3,
        note: 'three anchors (wave 1-2-3) project extension levels',
      },
      {
        id: 'fib_channel',
        label: 'Fib Channel',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 3,
        note: 'two anchors set baseline, third sets width for fib parallel channel',
      },
      {
        id: 'fib_time_zone',
        label: 'Fib Time Zone',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 2,
        note: 'two anchors set base unit, draws vertical fib time intervals',
      },
      {
        id: 'fib_speed_resistance_fan',
        label: 'Fib Speed Resistance Fan',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 2,
        note: 'two anchors define box, draws diagonal fib fan rays',
      },
      {
        id: 'trend_based_fib_time',
        label: 'Trend-Based Fib Time',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 3,
        note: 'three anchors project fib-spaced vertical time lines',
      },
      {
        id: 'fib_circles',
        label: 'Fib Circles',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 2,
        note: 'two anchors set center and radius for concentric fib circles',
      },
      {
        id: 'fib_spiral',
        label: 'Fib Spiral',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 2,
        note: 'two anchors set center and start, draws golden spiral',
      },
      {
        id: 'fib_wedge',
        label: 'Fib Wedge',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 3,
        note: 'three anchors define wedge with fib arc divisions',
      },
      {
        id: 'fib_speed_resistance_arcs',
        label: 'Fib Speed Resistance Arcs',
        group: 'gann_fibonacci',
        geometry: 'fib',
        clicks: 2,
        note: 'two anchors define base, draws fib resistance arcs',
      },
      {
        id: 'pitchfork',
        label: 'Pitchfork (Andrews)',
        group: 'gann_fibonacci',
        geometry: 'point3',
        clicks: 3,
        note: 'three pivot anchors define median line and parallel tines',
      },
      {
        id: 'schiff_pitchfork',
        label: 'Schiff Pitchfork',
        group: 'gann_fibonacci',
        geometry: 'point3',
        clicks: 3,
        note: 'three anchors; handle origin shifted to midpoint of 1-2',
      },
      {
        id: 'modified_schiff_pitchfork',
        label: 'Modified Schiff Pitchfork',
        group: 'gann_fibonacci',
        geometry: 'point3',
        clicks: 3,
        note: 'three anchors; modified Schiff handle placement',
      },
      {
        id: 'inside_pitchfork',
        label: 'Inside Pitchfork',
        group: 'gann_fibonacci',
        geometry: 'point3',
        clicks: 3,
        note: 'three anchors; tighter inside median variant',
      },
      {
        id: 'gann_box',
        label: 'Gann Box',
        group: 'gann_fibonacci',
        geometry: 'gann',
        clicks: 2,
        note: 'two anchors define box with Gann price/time grid',
      },
      {
        id: 'gann_square_fixed',
        label: 'Gann Square Fixed',
        group: 'gann_fibonacci',
        geometry: 'gann',
        clicks: 2,
        note: 'two anchors define fixed Gann square with diagonals',
      },
      {
        id: 'gann_square',
        label: 'Gann Square',
        group: 'gann_fibonacci',
        geometry: 'gann',
        clicks: 2,
        note: 'two anchors define scalable Gann square',
      },
      {
        id: 'gann_fan',
        label: 'Gann Fan',
        group: 'gann_fibonacci',
        geometry: 'gann',
        clicks: 2,
        note: 'two anchors define origin and 1x1, draws Gann angle rays',
      },
    ],
  },
  {
    id: 'patterns',
    label: 'Patterns',
    tools: [
      {
        id: 'xabcd_pattern',
        label: 'XABCD Pattern',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 5,
        note: 'five anchors X-A-B-C-D harmonic pattern',
      },
      {
        id: 'cypher_pattern',
        label: 'Cypher Pattern',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 5,
        note: 'five anchors for Cypher harmonic pattern',
      },
      {
        id: 'head_and_shoulders',
        label: 'Head and Shoulders',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 7,
        note: 'seven anchors trace shoulder-head-shoulder with neckline',
      },
      {
        id: 'abcd_pattern',
        label: 'ABCD Pattern',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 4,
        note: 'four anchors A-B-C-D pattern',
      },
      {
        id: 'triangle_pattern',
        label: 'Triangle Pattern',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 4,
        note: 'four anchors define triangle pattern legs',
      },
      {
        id: 'three_drives',
        label: 'Three Drives Pattern',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 7,
        note: 'seven anchors trace three-drive harmonic pattern',
      },
      {
        id: 'elliott_impulse',
        label: 'Elliott Impulse Wave (12345)',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 6,
        note: 'six anchors label five-wave impulse sequence',
      },
      {
        id: 'elliott_triangle',
        label: 'Elliott Triangle Wave (ABCDE)',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 6,
        note: 'six anchors label ABCDE triangle wave',
      },
      {
        id: 'elliott_triple_combo',
        label: 'Elliott Triple Combo Wave (WXYXZ)',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 6,
        note: 'six anchors label WXYXZ triple combination',
      },
      {
        id: 'elliott_double_combo',
        label: 'Elliott Double Combo Wave (WXY)',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 4,
        note: 'four anchors label WXY double combination',
      },
      {
        id: 'elliott_correction',
        label: 'Elliott Correction Wave (ABC)',
        group: 'patterns',
        geometry: 'pattern',
        clicks: 4,
        note: 'four anchors label ABC corrective wave',
      },
    ],
  },
  {
    id: 'projection',
    label: 'Projection',
    tools: [
      {
        id: 'long_position',
        label: 'Long Position',
        group: 'projection',
        geometry: 'range',
        clicks: 3,
        note: 'entry/stop/target anchors form risk-reward long box',
      },
      {
        id: 'short_position',
        label: 'Short Position',
        group: 'projection',
        geometry: 'range',
        clicks: 3,
        note: 'entry/stop/target anchors form risk-reward short box',
      },
      {
        id: 'forecast',
        label: 'Forecast',
        group: 'projection',
        geometry: 'range',
        clicks: 3,
        note: 'anchor plus projected end-range for scenario forecast',
      },
      {
        id: 'bars_pattern',
        label: 'Bars Pattern',
        group: 'projection',
        geometry: 'range',
        clicks: 2,
        note: 'select bar range then place copy elsewhere',
      },
      {
        id: 'ghost_feed',
        label: 'Ghost Feed',
        group: 'projection',
        geometry: 'range',
        clicks: 2,
        note: 'two anchors define synthetic editable candle range',
      },
      {
        id: 'projection',
        label: 'Projection',
        group: 'projection',
        geometry: 'range',
        clicks: 3,
        note: 'three anchors project price/time move forward',
      },
      {
        id: 'price_range',
        label: 'Price Range',
        group: 'projection',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors measure vertical price delta',
      },
      {
        id: 'date_range',
        label: 'Date Range',
        group: 'projection',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors measure horizontal bar/time delta',
      },
      {
        id: 'date_and_price_range',
        label: 'Date and Price Range',
        group: 'projection',
        geometry: 'range',
        clicks: 2,
        note: 'two anchors measure combined price and date delta box',
      },
    ],
  },
  {
    id: 'brushes',
    label: 'Brushes',
    tools: [
      {
        id: 'brush',
        label: 'Brush',
        group: 'brushes',
        geometry: 'brush',
        clicks: -1,
        note: 'freehand draw; press-drag-release, smoothed stroke',
      },
      {
        id: 'highlighter',
        label: 'Highlighter',
        group: 'brushes',
        geometry: 'brush',
        clicks: -1,
        note: 'freehand translucent highlight stroke, press-drag-release',
      },
    ],
  },
  {
    id: 'arrows',
    label: 'Arrows',
    tools: [
      {
        id: 'arrow_marker',
        label: 'Arrow Marker',
        group: 'arrows',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors define arrow with optional text label',
      },
      {
        id: 'arrow',
        label: 'Arrow',
        group: 'arrows',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors define start and head of a simple arrow',
      },
      {
        id: 'arrow_mark_up',
        label: 'Arrow Mark Up',
        group: 'arrows',
        geometry: 'placed',
        clicks: 1,
        note: 'single click drops an up arrow marker',
      },
      {
        id: 'arrow_mark_down',
        label: 'Arrow Mark Down',
        group: 'arrows',
        geometry: 'placed',
        clicks: 1,
        note: 'single click drops a down arrow marker',
      },
      {
        id: 'arrow_mark_left',
        label: 'Arrow Mark Left',
        group: 'arrows',
        geometry: 'placed',
        clicks: 1,
        note: 'single click drops a left arrow marker',
      },
      {
        id: 'arrow_mark_right',
        label: 'Arrow Mark Right',
        group: 'arrows',
        geometry: 'placed',
        clicks: 1,
        note: 'single click drops a right arrow marker',
      },
    ],
  },
  {
    id: 'shapes',
    label: 'Shapes',
    tools: [
      {
        id: 'rectangle',
        label: 'Rectangle',
        group: 'shapes',
        geometry: 'point2',
        clicks: 2,
        note: 'two opposite corner anchors define axis-aligned box',
      },
      {
        id: 'rotated_rectangle',
        label: 'Rotated Rectangle',
        group: 'shapes',
        geometry: 'point3',
        clicks: 3,
        note: 'two anchors set baseline, third sets height/rotation',
      },
      {
        id: 'ellipse',
        label: 'Ellipse',
        group: 'shapes',
        geometry: 'point2',
        clicks: 2,
        note: 'two anchors define bounding box of the ellipse',
      },
      {
        id: 'triangle',
        label: 'Triangle',
        group: 'shapes',
        geometry: 'point3',
        clicks: 3,
        note: 'three vertex anchors define triangle shape',
      },
      {
        id: 'arc',
        label: 'Arc',
        group: 'shapes',
        geometry: 'point3',
        clicks: 3,
        note: 'two anchors set chord, third sets curvature',
      },
      {
        id: 'curve',
        label: 'Curve',
        group: 'shapes',
        geometry: 'point3',
        clicks: 3,
        note: 'two endpoints plus control point bend a single curve',
      },
      {
        id: 'double_curve',
        label: 'Double Curve',
        group: 'shapes',
        geometry: 'point3',
        clicks: 3,
        note: 'anchors define an S-shaped double curve',
      },
      {
        id: 'polyline',
        label: 'Polyline',
        group: 'shapes',
        geometry: 'pointN',
        clicks: -1,
        note: 'click sequential vertices, double-click or esc to finish',
      },
      {
        id: 'path',
        label: 'Path',
        group: 'shapes',
        geometry: 'pointN',
        clicks: -1,
        note: 'multi-segment arrowed path, click vertices, double-click to finish',
      },
    ],
  },
  {
    id: 'text_notes',
    label: 'Text & notes',
    tools: [
      {
        id: 'text',
        label: 'Text',
        group: 'text_notes',
        geometry: 'text',
        clicks: 1,
        note: 'single click places editable free text box',
      },
      {
        id: 'anchored_text',
        label: 'Anchored Text',
        group: 'text_notes',
        geometry: 'text',
        clicks: 1,
        note: 'single click pins text to a chart coordinate',
      },
      {
        id: 'note',
        label: 'Note',
        group: 'text_notes',
        geometry: 'text',
        clicks: 1,
        note: 'single click drops a collapsible note marker',
      },
      {
        id: 'anchored_note',
        label: 'Anchored Note',
        group: 'text_notes',
        geometry: 'text',
        clicks: 1,
        note: 'single click pins a note to chart coordinate',
      },
      {
        id: 'callout',
        label: 'Callout',
        group: 'text_notes',
        geometry: 'point2',
        clicks: 2,
        note: 'anchor point plus pointer tail to a labeled bubble',
      },
      {
        id: 'comment',
        label: 'Comment',
        group: 'text_notes',
        geometry: 'text',
        clicks: 1,
        note: 'single click places a comment speech-bubble marker',
      },
      {
        id: 'price_label',
        label: 'Price Label',
        group: 'text_notes',
        geometry: 'point1',
        clicks: 1,
        note: 'single click pins a label showing the price at that point',
      },
      {
        id: 'signpost',
        label: 'Signpost',
        group: 'text_notes',
        geometry: 'point1',
        clicks: 1,
        note: 'single click drops a signpost flag with text on a stem',
      },
      {
        id: 'flag_mark',
        label: 'Flag Mark',
        group: 'text_notes',
        geometry: 'placed',
        clicks: 1,
        note: 'single click drops a flag marker',
      },
      {
        id: 'table',
        label: 'Table',
        group: 'text_notes',
        geometry: 'placed',
        clicks: 1,
        note: 'single click places an editable floating table overlay',
      },
    ],
  },
  {
    id: 'patterns_emojis_icons',
    label: 'Patterns, Emojis & Icons',
    tools: [
      {
        id: 'icon',
        label: 'Icon',
        group: 'patterns_emojis_icons',
        geometry: 'placed',
        clicks: 1,
        note: 'pick from icon library then single click to place',
      },
      {
        id: 'emoji',
        label: 'Emoji',
        group: 'patterns_emojis_icons',
        geometry: 'placed',
        clicks: 1,
        note: 'pick an emoji then single click to place',
      },
      {
        id: 'sticker',
        label: 'Sticker',
        group: 'patterns_emojis_icons',
        geometry: 'placed',
        clicks: 1,
        note: 'pick an animated sticker then single click to place',
      },
      {
        id: 'image',
        label: 'Image',
        group: 'patterns_emojis_icons',
        geometry: 'placed',
        clicks: 1,
        note: 'upload/select image then single click to place',
      },
    ],
  },
  {
    id: 'measure',
    label: 'Measure',
    tools: [
      {
        id: 'measure',
        label: 'Measure',
        group: 'measure',
        geometry: 'measure',
        clicks: 2,
        note: 'two anchors show price%, bar count and time delta, transient',
      },
    ],
  },
  {
    id: 'zoom',
    label: 'Zoom',
    tools: [
      {
        id: 'zoom_in',
        label: 'Zoom In',
        group: 'zoom',
        geometry: 'range',
        clicks: 2,
        note: 'drag a rectangle over the area to magnify into',
      },
      {
        id: 'zoom_out',
        label: 'Zoom Out',
        group: 'zoom',
        geometry: 'placed',
        clicks: 1,
        note: 'click to step the view zoom outward',
      },
    ],
  },
  {
    id: 'toggles',
    label: 'Tool toggles & global actions',
    tools: [
      {
        id: 'magnet_weak',
        label: 'Magnet (Weak)',
        group: 'toggles',
        geometry: 'placed',
        clicks: 0,
        note: 'toggle: snaps anchors to nearby OHLC when close',
      },
      {
        id: 'magnet_strong',
        label: 'Magnet (Strong)',
        group: 'toggles',
        geometry: 'placed',
        clicks: 0,
        note: 'toggle: always snaps anchors to nearest OHLC value',
      },
      {
        id: 'stay_in_drawing_mode',
        label: 'Stay in Drawing Mode',
        group: 'toggles',
        geometry: 'placed',
        clicks: 0,
        note: 'toggle: keep the active tool selected after each draw',
      },
      {
        id: 'lock_all_drawings',
        label: 'Lock All Drawings',
        group: 'toggles',
        geometry: 'placed',
        clicks: 0,
        note: 'toggle: prevent moving/editing existing drawings',
      },
      {
        id: 'hide_all_drawings',
        label: 'Hide All Drawings',
        group: 'toggles',
        geometry: 'placed',
        clicks: 0,
        note: 'toggle: hide/show all drawings without deleting them',
      },
      {
        id: 'remove_drawings_indicators',
        label: 'Remove Drawings & Indicators',
        group: 'toggles',
        geometry: 'placed',
        clicks: 0,
        note: 'action: bulk-delete drawings and/or indicators from chart',
      },
    ],
  },
]

// ---------------------------------------------------------------------------
// Derived flat structures
// ---------------------------------------------------------------------------

/** All 95 tool definitions in group order. */
export const ALL_TOOLS: ToolDef[] = TOOL_GROUPS.flatMap((g) => g.tools)

/** O(1) lookup by tool id. */
export const TOOL_BY_ID: Record<string, ToolDef> = Object.fromEntries(
  ALL_TOOLS.map((t) => [t.id, t]),
)

// ---------------------------------------------------------------------------
// Aliases / opaque types
// ---------------------------------------------------------------------------

/**
 * DrawTool is a tool id string. Using a branded alias keeps call-sites
 * readable without narrowing the runtime representation.
 */
export type DrawTool = string

// ---------------------------------------------------------------------------
// DEFAULT_TOOL_PER_GROUP
//
// For flyout menus: the "representative" tool shown on the toolbar button for
// each group. Strategy: first tool with geometry !== 'placed' OR clicks > 0;
// fall back to the first tool in the group.
// ---------------------------------------------------------------------------

export const DEFAULT_TOOL_PER_GROUP: Record<string, string> = Object.fromEntries(
  TOOL_GROUPS.map((g) => {
    const preferred =
      g.tools.find((t) => t.geometry !== 'placed' || t.clicks > 0) ?? g.tools[0]
    return [g.id, preferred.id]
  }),
)

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/**
 * Returns the number of discrete clicks required to complete placement.
 *
 * Rules (in priority order):
 * 1. geometry 'brush' or 'pointN'  → -1 (indefinite; ends on release / double-click / Esc)
 * 2. t.clicks > 0                  → t.clicks (spec value is authoritative)
 * 3. geometry 'placed' && clicks 0 → 0 (cursor/toggle mode, no placement)
 * 4. t.clicks === -1 (spec)        → -1 (indefinite, same as rule 1 path)
 * 5. fallback                      → t.clicks
 */
export function requiredClicks(t: ToolDef): number {
  if (t.geometry === 'brush' || t.geometry === 'pointN') return -1
  if (t.clicks > 0) return t.clicks
  if (t.geometry === 'placed' && t.clicks === 0) return 0
  return t.clicks
}

/**
 * Returns true when the tool produces a persistent spatial drawing that the
 * user must place on the chart. Returns false for pure cursors, toggles, and
 * global actions (geometry 'placed' with clicks === 0).
 */
export function isDrawable(geometry: Geometry): boolean {
  // Every geometry other than a zero-click 'placed' mode is drawable.
  // Note: 'placed' tools with clicks > 0 (e.g. eraser, arrow marks) ARE
  // drawable — they place a marker on click. Only clicks === 0 modes are
  // non-drawing.
  //
  // This function accepts geometry alone, so we conservatively treat all
  // non-'placed' geometries as drawable. For 'placed', the caller must
  // additionally check ToolDef.clicks === 0 to distinguish cursors from
  // single-click markers.
  return geometry !== 'placed'
}
