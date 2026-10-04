# Interactive Shiny for R front end for the MAA sectional meeting map.
#
# R twin of app.py: reads the CSV produced by the LangGraph pipeline
# (data/meetings_latest.csv) and renders a leaflet map plus a data table
# with live filters. Temporal buckets (past / current term / upcoming) are
# recomputed at app start, so the colors shift as time passes without
# re-running the pipeline.
#
# Run from this directory:
#
#     Rscript -e 'shiny::runApp(".", port = 8130)'
#
# Export for GitHub Pages (from the repo root):
#
#     Rscript -e 'shinylive::export("shinylive_r_app", "site/shinylive-r")'

library(shiny)
library(bslib)
library(leaflet)
library(htmltools)

source("meeting_time.R")  # pure logic: time buckets, fade, regions, filter

DATA_PATH <- "data/meetings_latest.csv"
SECTION_GROUPS_PATH <- "data/section_groups.csv"
LAST_RUN_PATH <- "data/last_run.txt"
SOURCE_URL <- "https://maa.org/section-meetings/"
REPO_URL <- "https://github.com/youngsu-Kim/maa_sectional_meetings_map"

STATUS_COLORS <- c(
  past = "lightgray",     # light grey
  current = "orange",     # current term
  upcoming = "green",     # upcoming terms
  mathfest = "darkpurple" # national meetings (MathFest)
)

STATUS_LABELS <- c(
  current = "Current term",
  upcoming = "Upcoming",
  mathfest = "MathFest",
  past = "Past"
)

txt <- function(value) {
  if (length(value) == 0L || is.null(value) || is.na(value)) "" else as.character(value)
}

load_meetings <- function(today) {
  df <- read.csv(DATA_PATH, stringsAsFactors = FALSE)
  df <- df[df$status == "ok" & !is.na(df$latitude), , drop = FALSE]
  df$latitude <- as.numeric(df$latitude)
  df$longitude <- as.numeric(df$longitude)
  # Buckets are relative to *now*, so the app stays current between runs.
  # National meetings (row_id national-*) form their own MathFest category.
  df$bucket <- vapply(as.character(df$date), function(d) meeting_status(d, today),
                      character(1), USE.NAMES = FALSE)
  df$bucket[startsWith(as.character(df$row_id), "national-")] <- "mathfest"
  rownames(df) <- NULL
  df
}

popup_html <- function(row) {
  note <- txt(row[["note"]])
  note_line <- if (nzchar(note)) paste0("<i>&dagger; ", note, "</i><br>") else ""
  speakers_html <- paste0(vapply(speaker_lines(row[["speakers"]]), function(s) {
    if (is.null(s$color)) paste0(s$name, "<br>")
    else paste0('<span style="color:', s$color, ';">', s$name, "</span><br>")
  }, character(1), USE.NAMES = FALSE), collapse = "")
  url <- txt(row[["section_url"]])
  paste0(
    "<b>", txt(row[["section"]]), "</b> (", term_label(txt(row[["date"]])), ")<br>",
    normalize_date(txt(row[["date"]])), "<br>",
    txt(row[["location"]]), "<br>",
    note_line,
    speakers_html,
    "<a href='", url, "' target='_blank' rel='noopener noreferrer'>", url, "</a>"
  )
}

build_map <- function(view, today) {
  m <- leaflet(view, options = leafletOptions(maxZoom = 19)) |>
    setView(lng = -98.35, lat = 39.5, zoom = 4)
  # Basemaps: standard OSM, plus Esri satellite imagery for street-level
  # detail when zoomed in; the switcher (bottom-right) toggles them.
  # Satellite is added first but hidden, so Standard shows by default.
  m <- addProviderTiles(m, providers$Esri.WorldImagery, group = "Satellite",
                        options = providerTileOptions(maxZoom = 19))
  m <- addTiles(m, group = "Standard", options = tileOptions(maxZoom = 19))
  m <- hideGroup(m, "Satellite")
  m <- addLayersControl(m, baseGroups = c("Standard", "Satellite"),
                        options = layersControlOptions(collapsed = FALSE),
                        position = "bottomright")

  # Future pins fade with temporal distance: the soonest upcoming (and the
  # soonest MathFest) meeting stays fully opaque, later ones get lighter.
  # Upcoming fades gently (never as faint as past); MathFest fades steeper.
  # Past pins use a constant dimmed opacity.
  alpha <- rep(1, nrow(view))
  if (nrow(view)) {
    for (b in c("upcoming", "mathfest")) {
      idx <- which(view$bucket == b)
      if (length(idx)) {
        ramp <- if (identical(b, "upcoming")) UPCOMING_RAMP else NATIONAL_RAMP
        alpha[idx] <- fade_alphas(as.character(view$date[idx]), ramp)
      }
    }
    idx <- which(view$bucket == "past")
    if (length(idx)) alpha[idx] <- PAST_ALPHA
  }

  if (nrow(view)) {
    # Vectorized awesomeIcons: the leaflet JS builds a dataframe from the
    # icon fields and reads row i per marker, so every field must be a
    # full-length, *unnamed* vector (named vectors serialize as objects).
    icons <- awesomeIcons(
      markerColor = unname(STATUS_COLORS[view$bucket]),
      icon = rep("info-sign", nrow(view)),
      library = rep("glyphicon", nrow(view))
    )
    popups <- vapply(seq_len(nrow(view)), function(i) popup_html(view[i, ]),
                     character(1), USE.NAMES = FALSE)
    m <- addAwesomeMarkers(m, lng = ~longitude, lat = ~latitude,
                           icon = icons,
                           options = markerOptions(opacity = alpha),
                           popup = popups)
  }
  if (nrow(view) >= 2) {
    m <- fitBounds(m, lng1 = min(view$longitude), lat1 = min(view$latitude),
                   lng2 = max(view$longitude), lat2 = max(view$latitude))
  }
  legend <- paste0(
    '<span style="color:orange;">&#9679;</span> Current term (',
    current_term_label(today), ')&nbsp;&nbsp;',
    '<span style="color:green;">&#9679;</span> Upcoming&nbsp;&nbsp;',
    '<span style="color:darkpurple;">&#9679;</span> MathFest&nbsp;&nbsp;',
    '<span style="color:lightgray;">&#9679;</span> Past'
  )
  addControl(m, html = HTML(paste0(
    '<div style="background: rgba(255, 255, 255, 0.92); padding: 6px 10px; ',
    'border: 1px solid #999; border-radius: 4px; font-size: 12px; ',
    'line-height: 1.8;">', legend, "</div>"
  )), position = "topright")
}

table_html <- function(view, sortby) {
  key_y <- vapply(as.character(view$date),
                  function(d) meeting_sort_key(d)[1L], integer(1), USE.NAMES = FALSE)
  key_m <- vapply(as.character(view$date),
                  function(d) meeting_sort_key(d)[2L], integer(1), USE.NAMES = FALSE)
  ord <- if (identical(sortby, "section")) {
    order(view$section, key_y, key_m, method = "radix")
  } else {
    order(key_y, key_m, method = "radix")
  }
  view <- view[ord, , drop = FALSE]

  # MathFest dots echo the map pins' fade (same NATIONAL_RAMP), so the
  # table shows at a glance which MathFests are nearer.
  mf_alpha <- rep(1, nrow(view))
  mf_idx <- which(view$bucket == "mathfest")
  if (length(mf_idx)) {
    mf_alpha[mf_idx] <- fade_alphas(as.character(view$date[mf_idx]), NATIONAL_RAMP)
  }

  head_row <- tags$thead(tags$tr(
    tags$th("Section"), tags$th("Date"), tags$th("Location"), tags$th("Speakers"),
    tags$th("When", style = "text-align: center;")
  ))
  body_rows <- lapply(seq_len(nrow(view)), function(i) {
    row <- view[i, ]
    section <- txt(row$section)
    url <- txt(row$section_url)
    section_cell <- if (startsWith(url, "http")) {
      tags$a(section, href = url, target = "_blank", rel = "noopener noreferrer")
    } else {
      section
    }
    bucket <- txt(row$bucket)
    speakers_cell <- lapply(speaker_lines(row$speakers), function(s) {
      if (is.null(s$color)) tags$div(s$name)
      else tags$div(s$name, style = paste0("color: ", s$color, ";"))
    })
    location_text <- txt(row$location)
    location_note <- txt(row$note)
    location_children <- list()
    if (nzchar(location_text) && !is.na(row$latitude) && row$latitude != 0 &&
        !is.na(row$longitude) && row$longitude != 0) {
      location_children[[length(location_children) + 1L]] <- tags$a(
        location_text,
        href = paste0("https://www.google.com/maps/search/?api=1&query=",
                      row$latitude, ",", row$longitude),
        target = "_blank", rel = "noopener noreferrer"
      )
    } else if (nzchar(location_text)) {
      location_children[[length(location_children) + 1L]] <- location_text
    }
    if (nzchar(location_text) && nzchar(location_note)) {
      # dagger marks a corrected location; hover explains the fix
      location_children[[length(location_children) + 1L]] <- tags$sup(
        "\u2020", title = location_note, style = "color: #6c757d; cursor: help;"
      )
    }
    dot_color <- if (bucket %in% names(STATUS_COLORS)) STATUS_COLORS[[bucket]] else "black"
    dot_style <- paste0("color: ", dot_color, ";")
    if (mf_alpha[i] < 1.0) {
      dot_style <- paste0(dot_style, " opacity: ", mf_alpha[i], ";")
    }
    tags$tr(
      tags$td(section_cell),
      tags$td(normalize_date(txt(row$date))),
      tags$td(location_children),
      tags$td(speakers_cell),
      tags$td(
        tags$span("\u25cf", style = dot_style, title = bucket),
        style = "text-align: center;"
      )
    )
  })
  tags$div(
    tags$table(
      head_row,
      do.call(tags$tbody, body_rows),
      class = "table table-striped table-sm mb-0",
      style = "font-size: 0.85em;"
    ),
    style = "height: 100%; overflow-y: auto;"
  )
}

TODAY <- Sys.Date()
MEETINGS <- load_meetings(TODAY)
REGION_BY_SECTION <- region_map(SECTION_GROUPS_PATH)
MEETINGS$region <- vapply(MEETINGS$section, region_of,
                          character(1), USE.NAMES = FALSE,
                          region_by_section = REGION_BY_SECTION)
# Combined "Section (Region)" haystack: lets a region word filter by region.
MEETINGS$search <- search_haystack(MEETINGS$section, MEETINGS$region)
SECTION_CHOICES <- grouped_section_choices(MEETINGS$section, REGION_BY_SECTION)
COLLECTED <- collected_line(LAST_RUN_PATH)

app_css <- paste0(
  "aside.sidebar { font-size: 0.85em; } ",
  # Bootstrap sets rem-based sizes on headings and form controls, which
  # ignore the parent's em; force them to inherit the sidebar's size.
  # Keep bslib's default 24px column gap; only tighten the hr margins
  # (Bootstrap's 2rem default was the worst offender).
  "aside select.form-select, aside select.shiny-input-select, ",
  "aside .selectize-input, aside .selectize-input input ",
  "{ font-size: inherit; } ",
  "aside h3 { font-size: 1.15em; font-weight: 600; line-height: 1.3; } ",
  "aside hr { margin: 0.55rem 0; } ",
  "aside #sortby { margin-bottom: 0.75rem; } ",
  # \\vfill: pin the footer to the sidebar bottom. The aside IS
  # .sidebar; make it a flex column, let the content box fill it,
  # and the footer rides an auto top margin -- pure CSS, so it
  # tracks window resizes with no JS needed.
  "aside.sidebar { display: flex; flex-direction: column; } ",
  "aside .sidebar-content { flex: 1 1 auto; } ",
  "aside .sidebar-content > .sidebar-footer { margin-top: auto !important; } ",
  "#pane_resizer { height: 16px; flex: none; cursor: row-resize; ",
  "display: flex; align-items: center; } ",
  "#pane_resizer::after { content: ''; width: 100%; height: 5px; ",
  "border-radius: 3px; background: #dee2e6; } ",
  "#pane_resizer:hover::after, #pane_resizer:active::after ",
  "{ background: #adb5bd; } ",
  "#table_card { flex: 1 1 auto; min-height: 200px; display: flex; ",
  "flex-direction: column; overflow: hidden; } ",
  "#table_card .card-body { flex: 1 1 auto; min-height: 0; ",
  "overflow: hidden; } ",
  "#table_card #table { height: 100%; } ",
  # Map pane: 62% of the VISIBLE window. dvh (not vh) matters in
  # Safari, where 100vh includes the area under the URL bar and
  # would push the table below the fold; the vh line is the
  # fallback for engines without dvh support.
  "#map_card { height: clamp(240px, 62vh, calc(100vh - 240px)); } ",
  "#map_card { height: clamp(240px, 62dvh, calc(100dvh - 240px)); } ",
  # Bind the layout into the grid row's fixed height: bslib nests
  # main inside a .main div, so pin both, and let the wrapper fill
  # it, so the table pane only gets what the window actually has.
  ".bslib-sidebar-layout > .main { height: 100%; min-height: 0; ",
  "display: flex; flex-direction: column; overflow: hidden; } ",
  ".bslib-sidebar-layout > .main > .bslib-page-main { flex: 1 1 auto; ",
  "min-height: 0; display: flex; flex-direction: column; } ",
  ".bslib-page-main > div { flex: 1 1 auto; min-height: 0; }"
)

# Checkbox labels carrying the map pin colors: '● Past', ...
bucket_choice_names <- lapply(names(STATUS_LABELS), function(b) {
  text <- STATUS_LABELS[[b]]
  if (identical(b, "current")) {
    text <- paste0("Current term (", current_term_label(TODAY), ")")
  }
  HTML(paste0('<span style="color: ', STATUS_COLORS[[b]], ';">&#9679;</span> ', text))
})
names(bucket_choice_names) <- names(STATUS_LABELS)

sidebar_ui <- bslib::sidebar(
  tags$style(HTML(app_css)),
  # Title + disclaimer as one block: inside the wrapper they sit 2px
  # apart instead of getting the sidebar's 24px flex gap between them.
  tags$div(
    style = "display: flex; flex-direction: column; gap: 2px;",
    tags$h3("MAA Sectional Meetings"),
    tags$p(
      "Unofficial extract of ",
      tags$a("MAA webpage", href = SOURCE_URL, target = "_blank",
             rel = "noopener noreferrer"),
      if (!is.null(COLLECTED)) {
        # display:block keeps it on its own line with a much tighter
        # leading than a <br> would give.
        tags$span(COLLECTED,
                  style = "display: block; margin-top: 2px; line-height: 1.2;")
      }
    )
  ),
  tags$hr(),
  checkboxGroupInput(
    "buckets",
    label = NULL,  # label omitted; the hr separators + colored dots speak for it
    choiceNames = unname(bucket_choice_names),
    choiceValues = unname(names(STATUS_LABELS)),
    selected = c("current", "upcoming", "mathfest")
  ),
  tags$hr(),
  # Searchable dropdown with region divider headers; `create` lets any
  # free text (e.g. the region word "west") be committed with Enter and
  # is matched by the filter below. Exact names still filter instantly.
  selectizeInput(
    "section",
    "Filter by section",
    choices = SECTION_CHOICES,
    selected = "All",
    options = list(create = TRUE)
  ),
  tags$hr(),
  radioButtons(
    "sortby",
    "Sort by",
    choices = c("Date" = "date", "Section" = "section"),
    selected = "section",
    inline = TRUE
  ),
  tags$hr(),
  tags$p(
    style = "margin-bottom: 0; line-height: 1.25;",
    class = "sidebar-footer",
    "Created by ",
    tags$a("Youngsu Kim", href = REPO_URL, target = "_blank",
           rel = "noopener noreferrer"),
    tags$span(
      style = "display: block;",
      "Source: ",
      tags$a("maa.org/section-meetings", href = SOURCE_URL, target = "_blank",
             rel = "noopener noreferrer")
    )
  ),
  width = 280
)

# Map on top, table below, split by a draggable divider (like the sidebar
# edge), together filling the viewport height. Pure DOM/JS so it behaves
# identically under Shinylive/webR; Leaflet re-measures its map on divider
# drags and on any container/window size change.
resizer_js <- "
(function () {
  function invalidate() {
    try {
      var el = document.getElementById('map');
      if (!el || !window.HTMLWidgets) return;
      var inst = HTMLWidgets.find(el);
      if (!inst) return;
      var m = inst.getMap ? inst.getMap() : inst;
      if (m && typeof m.invalidateSize === 'function') m.invalidateSize();
    } catch (e) {}
  }
  function bind() {
    var card = document.getElementById('map_card');
    var grip = document.getElementById('pane_resizer');
    if (!card || !grip || grip.dataset.bound) return;
    grip.dataset.bound = '1';
    var startY = 0, startH = 0, dragging = false;
    function maxCardH() {
      // never starve the table pane below 200px
      return Math.max(240, card.parentElement.clientHeight
        - grip.offsetHeight - 200);
    }
    grip.addEventListener('pointerdown', function (e) {
      dragging = true;
      startY = e.clientY;
      startH = card.getBoundingClientRect().height;
      try { grip.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
    });
    grip.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var h = Math.min(
        Math.max(startH + (e.clientY - startY), 240),
        maxCardH()
      );
      card.style.height = h + 'px';
    });
    function stop() {
      if (!dragging) return;
      dragging = false;
      invalidate();
    }
    grip.addEventListener('pointerup', stop);
    grip.addEventListener('pointercancel', stop);
    // The cards already stretch with the window, but Leaflet keeps
    // the tile view it measured at build time; re-measure on resize
    // so the map fills the card's (re)computed width/height. Also
    // re-clamp a previously dragged height when the window shrinks.
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        var h = card.getBoundingClientRect().height;
        var cap = maxCardH();
        if (card.style.height && h > cap) card.style.height = cap + 'px';
        invalidate();
      }, 150);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  }
  window.addEventListener('load', bind);
  document.addEventListener('shiny:connected', bind);
  setTimeout(bind, 300);
  setTimeout(bind, 1500);
})();
"

main_ui <- tags$div(
  style = "display: flex; flex-direction: column; min-height: 0; flex: 1 1 auto;",
  tags$div(
    id = "map_card", class = "card bslib-card",
    style = paste0("height: clamp(240px, 62vh, calc(100vh - 240px)); ",
                   "min-height: 240px; flex: 0 0 auto; margin-bottom: 0;"),
    bslib::card_body(leafletOutput("map", width = "100%", height = "100%"))
  ),
  tags$div(id = "pane_resizer"),
  tags$div(
    id = "table_card", class = "card bslib-card",
    tags$div(class = "card-header", "Meetings"),
    bslib::card_body(uiOutput("table"))
  ),
  tags$script(HTML(resizer_js))
)

ui <- bslib::page_sidebar(
  main_ui,
  sidebar = sidebar_ui,
  title = NULL,
  window_title = "MAA Sectional Meetings"
)

server <- function(input, output, session) {
  filtered <- reactive({
    view <- MEETINGS[MEETINGS$bucket %in% input$buckets, , drop = FALSE]
    # A chosen or typed region name filters by exact membership; anything
    # else is a word-start search over "Section (Region)". "All"/blank
    # matches everything. (Logic + edge cases live in meeting_time.R.)
    view[section_filter_mask(input$section, view$region, view$search), ,
         drop = FALSE]
  })

  output$map <- renderLeaflet({
    build_map(filtered(), TODAY)
  })

  output$table <- renderUI({
    table_html(filtered(), input$sortby)
  })
}

shinyApp(ui, server)
