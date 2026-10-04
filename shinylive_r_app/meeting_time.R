# Time-relative classification of MAA meeting dates, plus the pure logic
# helpers shared by the R front end (regions, section filter, table text).
#
# Base R only on purpose: this module is sourced by app.R and by
# selftest.R, mirroring the role of meeting_time.py on the Python side
# (which is kept byte-identical between app.py and shinylive_app/).
# Here it is the single canonical copy: app.R sources it at runtime.

MONTH_RE <- paste0(
  "(?i)\\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|",
  "jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|",
  "dec(?:ember)?)\\b"
)
YEAR_RE <- "20[0-9]{2}"
MONTH_ABBR_PERIOD_RE <- "\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[.]"

MONTH_NUMBERS <- c(
  jan = 1L, feb = 2L, mar = 3L, apr = 4L, may = 5L, jun = 6L,
  jul = 7L, aug = 8L, sep = 9L, oct = 10L, nov = 11L, dec = 12L
)

FALL_MONTHS <- c("jul", "aug", "sep", "oct", "nov", "dec")
SPRING_MONTHS <- c("jan", "feb", "mar", "apr", "may", "jun")


normalize_date <- function(date) {
  # 'March 27-28, 2026' -> 'Mar 27-28, 2026'; 'Feb. 20-21, 2026' -> 'Feb 20-21, 2026'.
  if (!is.character(date) || length(date) != 1L || is.na(date)) return(date)
  out <- date
  hits <- regmatches(out, gregexpr(MONTH_RE, out, perl = TRUE))[[1]]
  if (length(hits)) {
    abbr <- vapply(hits, function(s) {
      p <- tolower(substr(s, 1L, 3L))
      paste0(toupper(substr(p, 1L, 1L)), substr(p, 2L, 3L))
    }, character(1), USE.NAMES = FALSE)
    regmatches(out, gregexpr(MONTH_RE, out, perl = TRUE)) <- list(abbr)
  }
  # Drop periods directly after the abbreviation ("Feb. 20" -> "Feb 20").
  gsub(MONTH_ABBR_PERIOD_RE, "\\1", out, perl = TRUE)
}


term_of <- function(date) {
  # 'fall' or 'spring' ("" if undeterminable). July/August count as fall,
  # matching the academic-term ordering used by meeting_status.
  hits <- regmatches(date, gregexpr(MONTH_RE, date, perl = TRUE))[[1]]
  months <- tolower(substr(hits, 1L, 3L))
  if (length(months)) {
    if (any(months %in% FALL_MONTHS)) return("fall")
    if (any(months %in% SPRING_MONTHS)) return("spring")
  }
  text <- tolower(date)
  if (grepl("fall", text, fixed = TRUE)) return("fall")
  if (grepl("spring", text, fixed = TRUE)) return("spring")
  ""
}


term_label <- function(date) {
  # Human label like 'Fall 2026'; falls back to the raw date text.
  term <- term_of(date)
  if (!nzchar(term)) return(date)
  year <- regmatches(date, regexpr(YEAR_RE, date))
  nice <- paste0(toupper(substr(term, 1L, 1L)), substr(term, 2L, nchar(term)))
  if (length(year)) paste(nice, year) else nice
}


parse_month_year <- function(date_str) {
  hits <- regmatches(date_str, gregexpr(MONTH_RE, date_str, perl = TRUE))[[1]]
  year <- regmatches(date_str, regexpr(YEAR_RE, date_str))
  if (!length(hits) || !length(year)) return(NULL)
  c(as.integer(year), MONTH_NUMBERS[[tolower(substr(hits[1L], 1L, 3L))]])
}


term_key <- function(year, month) {
  # Academic-year ordering: Fall 2026 < Spring 2027 < Fall 2027 < ...
  if (month <= 6L) c(year - 1L, 1L) else c(year, 0L)
}


current_term_label <- function(today = Sys.Date()) {
  y <- as.integer(format(today, "%Y"))
  m <- as.integer(format(today, "%m"))
  if (m <= 6L) paste("Spring", y) else paste("Fall", y)
}


meeting_sort_key <- function(date_str) {
  # Chronological sort key c(year, month); unparseable dates sort last.
  parsed <- parse_month_year(date_str)
  if (is.null(parsed)) c(9999L, 12L) else parsed
}


lex_less <- function(a, b) a[1L] < b[1L] || (a[1L] == b[1L] && a[2L] < b[2L])


meeting_status <- function(date_str, today = Sys.Date()) {
  # Bucket a meeting as 'past', 'current', or 'upcoming' relative to today,
  # at term granularity (Fall = Jul-Dec, Spring = Jan-Jun).
  parsed <- parse_month_year(date_str)
  if (is.null(parsed)) return("current")  # unparseable dates stay visible
  year <- parsed[1L]
  month <- parsed[2L]
  ty <- as.integer(format(today, "%Y"))
  tm <- as.integer(format(today, "%m"))
  if (lex_less(c(year, month), c(ty, tm))) return("past")
  mk <- term_key(year, month)
  tk <- term_key(ty, tm)
  if (lex_less(mk, tk)) return("past")
  if (identical(mk, tk)) return("current")
  "upcoming"
}


# Pin opacity by temporal rank within a bucket: soonest fully solid, then a
# hand-tuned fade. Ranks past the end of the ramp keep the last value.
# UPCOMING fades gently and never reaches PAST_ALPHA, so far-future pins do
# not look "past"; NATIONAL (MathFest) has exactly a handful of dates and
# uses the steeper requested ramp.
UPCOMING_RAMP <- c(1.0, 0.85, 0.75, 0.65)
NATIONAL_RAMP <- c(1.0, 0.70, 0.55, 0.45)
# Past meetings get a constant dimmed opacity, strictly below both ramps so
# they never blend into the faintest future pins.
PAST_ALPHA <- 0.40


fade_alphas <- function(dates, ramp = UPCOMING_RAMP) {
  # Pin opacity per date: soonest = ramp[1], later ranks fade along the
  # ramp. Ties (same year/month) share the same alpha. Input order is
  # preserved in the output.
  n <- length(dates)
  if (n == 0L) return(numeric(0))
  keys <- lapply(as.character(dates), meeting_sort_key)
  yr <- vapply(keys, function(k) k[1L], integer(1), USE.NAMES = FALSE)
  mo <- vapply(keys, function(k) k[2L], integer(1), USE.NAMES = FALSE)
  ord <- order(yr, mo, method = "radix")
  alphas <- rep(1, n)
  distinct <- -1L
  prev_y <- NA_integer_
  prev_m <- NA_integer_
  for (i in ord) {
    if (is.na(prev_y) || yr[i] != prev_y || mo[i] != prev_m) {
      distinct <- distinct + 1L
      prev_y <- yr[i]
      prev_m <- mo[i]
    }
    alphas[i] <- ramp[min(distinct, length(ramp) - 1L) + 1L]
  }
  alphas
}


# --- Region grouping and section filtering --------------------------------
# MAA lists its sections flat; the larger regions in section_groups.csv are
# our own construct. Regions become the divider headers in the section
# filter, and the filter also matches region words. Sections absent from
# the CSV fall back to "Other".

REGION_ORDER <- c("Northeast", "Midwest", "South", "West", "National", "Other")


region_map <- function(path) {
  # Named character vector: region by section. Empty if the file is absent.
  if (!file.exists(path)) return(character(0))
  df <- read.csv(path, stringsAsFactors = FALSE)
  df <- df[!duplicated(df$section, fromLast = TRUE), , drop = FALSE]
  setNames(as.character(df$region), as.character(df$section))
}


region_of <- function(section, region_by_section) {
  r <- unname(region_by_section[section])
  if (length(r) != 1L || is.na(r)) "Other" else r
}


search_haystack <- function(section, region) {
  # Combined "Section (Region)" haystack: lets a region word filter by region.
  paste0(section, " (", region, ")")
}


grouped_section_choices <- function(sections, region_by_section,
                                    region_order = REGION_ORDER) {
  # Optgroup choices: region divider headers with plain section names.
  # A leading "Regions" divider makes each region itself selectable
  # ("All of West"), mirroring what typing the region word + Enter does.
  groups <- vector("list", length(region_order))
  names(groups) <- region_order
  for (sec in sort(unique(sections))) {
    reg <- region_of(sec, region_by_section)
    if (is.null(groups[[reg]])) groups[[reg]] <- character(0)
    groups[[reg]] <- c(groups[[reg]], sec)
  }
  choices <- list()
  choices[["All"]] <- "All"
  # NOTE: R shiny choice lists are c(<label> = <value>) -- mirrored from
  # Python shiny's {<value>: <label>}. So a region entry "All of West"=West
  # sends the region name as the input value, which the filter matches by
  # exact membership.
  region_opts <- list()
  for (r in region_order) {
    if (identical(r, "Other")) next
    if (length(groups[[r]])) region_opts[[paste("All of", r)]] <- r
  }
  if (length(region_opts)) choices[["Regions"]] <- region_opts
  order_all <- c(region_order, setdiff(names(groups), region_order))
  for (r in order_all) {
    if (length(groups[[r]])) {
      choices[[r]] <- setNames(as.list(groups[[r]]), groups[[r]])
    }
  }
  choices
}


regex_escape <- function(term) {
  gsub("([][{}()*+.?^$|\\\\])", "\\\\\\1", term, perl = TRUE)
}


section_filter_mask <- function(raw, regions, haystacks,
                                region_order = REGION_ORDER) {
  # A chosen or typed region name filters by exact membership (so "South"
  # does not leak into SOUTHWESTERN); anything else is a search: each term
  # must match at a word start in the combined "Section (Region)" haystack,
  # case-insensitively. "All"/blank matches everything.
  n <- length(haystacks)
  if (is.null(raw)) raw <- ""
  text <- tolower(trimws(as.character(raw)))
  if (!nzchar(text) || identical(text, "all")) return(rep(TRUE, n))
  exact <- region_order[tolower(region_order) == text]
  if (length(exact) == 1L) return(regions == exact)
  hay <- tolower(as.character(haystacks))
  keep <- rep(TRUE, n)
  for (term in strsplit(text, "\\s+")[[1]]) {
    keep <- keep & grepl(paste0("(?<!\\w)", regex_escape(term)), hay,
                         perl = TRUE)
  }
  keep
}


# --- Speaker-program tags (color-coded in the table and popups) -----------

SPEAKER_TYPE_COLORS <- c(
  visitor = "#b45309",  # amber (blue read as a hyperlink)
  polya = "#9467bd",    # purple
  nam = "#d62728",      # red
  awm = "#2ca02c"       # green
)
SPEAKER_TAG_RE <- "\\(([^)]+)\\)[[:space:]]*$"


speaker_lines <- function(speakers) {
  # One list(name, color) per speaker; color matches the program tag if any.
  text <- as.character(speakers)
  if (!length(text) || is.na(text) || !nzchar(text)) return(list())
  parts <- trimws(strsplit(text, ",")[[1]])
  parts <- parts[nzchar(parts)]
  lapply(parts, function(p) {
    color <- NULL
    m <- regmatches(p, regexec(SPEAKER_TAG_RE, p, perl = TRUE))[[1]]
    if (length(m) == 2L) {
      hit <- unname(SPEAKER_TYPE_COLORS[tolower(m[2L])])
      if (length(hit) == 1L && !is.na(hit)) color <- hit
    }
    list(name = p, color = color)
  })
}


collected_line <- function(path) {
  # 'Data collected: Oct 2, 2026' from the pipeline's last_run.txt.
  if (!file.exists(path)) return(NULL)
  txt <- trimws(readLines(path, warn = FALSE)[1])
  d <- tryCatch(as.Date(txt), error = function(e) NULL)
  if (is.null(d) || is.na(d)) return(NULL)
  paste0(
    "Data collected: ",
    month.abb[as.integer(format(d, "%m"))], " ",
    as.integer(format(d, "%d")), ", ",
    as.integer(format(d, "%Y"))
  )
}
