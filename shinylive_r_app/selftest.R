# Plain-Rscript regression tests for meeting_time.R (no testthat needed).
# Run from anywhere:  Rscript shinylive_r_app/selftest.R

args <- commandArgs(FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
self_dir <- if (length(file_arg)) {
  dirname(normalizePath(sub("^--file=", "", file_arg[1])))
} else {
  getwd()
}
source(file.path(self_dir, "meeting_time.R"))

failures <- 0
check <- function(label, value, expected) {
  ok <- identical(value, expected) || isTRUE(all.equal(value, expected))
  if (!ok) {
    failures <<- failures + 1
    cat("FAIL:", label, "\n  got:     ", deparse(value), "\n  expected:", deparse(expected), "\n")
  }
}

# --- normalize_date ---------------------------------------------------------
check("normalize full month", normalize_date("March 27-28, 2026"), "Mar 27-28, 2026")
check("normalize dotted abbr", normalize_date("Feb. 20-21, 2026"), "Feb 20-21, 2026")
check("normalize upper", normalize_date("SEPTEMBER 5, 2026"), "Sep 5, 2026")
check("normalize sept", normalize_date("Sept. 4, 2026"), "Sep 4, 2026")
check("no month unchanged", normalize_date("TBA 2026"), "TBA 2026")

# --- term_of / term_label ---------------------------------------------------
check("term fall by month", term_of("Oct 3-4, 2026"), "fall")
check("term spring by month", term_of("Mar 2027"), "spring")
check("term fall by word", term_of("Fall meeting"), "fall")
check("term spring by word", term_of("Spring fling"), "spring")
check("term unknown", term_of("TBA"), "")
check("term label with year", term_label("Oct 3-4, 2026"), "Fall 2026")
check("term label no year", term_label("Fall gathering"), "Fall")
check("term label fallback", term_label("TBA"), "TBA")

# --- meeting_sort_key -------------------------------------------------------
check("sort key parses", meeting_sort_key("Mar 14-15, 2026"), c(2026L, 3L))
check("sort key unparseable last", meeting_sort_key("TBA"), c(9999L, 12L))
check("current term label", current_term_label(as.Date("2026-10-02")), "Fall 2026")
check("current term label spring", current_term_label(as.Date("2027-02-01")), "Spring 2027")

# --- meeting_status (today fixed like the pytest suite) ---------------------
TODAY <- as.Date("2026-10-02")
check("status current month", meeting_status("Oct 3-4, 2026", TODAY), "current")
check("status same term later", meeting_status("Nov 2026", TODAY), "current")
check("status last month", meeting_status("Sep 12, 2026", TODAY), "past")
check("status summer past", meeting_status("Aug 2026", TODAY), "past")
check("status spring past", meeting_status("Jun 2026", TODAY), "past")
check("status next spring", meeting_status("Jan 2027", TODAY), "upcoming")
check("status far future", meeting_status("May 2027", TODAY), "upcoming")
check("status unparseable current", meeting_status("TBA", TODAY), "current")

# --- fade ramps -------------------------------------------------------------
check("upcoming ramp monotone", all(diff(UPCOMING_RAMP) < 0), TRUE)
check("national ramp monotone", all(diff(NATIONAL_RAMP) < 0), TRUE)
check("upcoming above past", min(UPCOMING_RAMP) > PAST_ALPHA, TRUE)
check("national above past", min(NATIONAL_RAMP) > PAST_ALPHA, TRUE)

check("fade empty", fade_alphas(character(0)), numeric(0))
check("fade single", fade_alphas("Mar 2027"), 1.0)
check("fade order preserved",
      fade_alphas(c("Mar 2027", "Oct 2026", "Jan 2027")),
      c(0.75, 1.0, 0.85))
check("fade ties share alpha",
      fade_alphas(c("Mar 2026", "Oct 2026", "Mar 2026")),
      c(1.0, 0.85, 1.0))
check("fade clamps at ramp end",
      fade_alphas(c("Jan 2027", "Feb 2027", "Mar 2027", "Apr 2027",
                    "May 2027", "Jun 2027")),
      c(1.0, 0.85, 0.75, 0.65, 0.65, 0.65))
check("fade national ramp",
      fade_alphas(c("Jul 2026", "Jul 2027", "Jul 2028"), NATIONAL_RAMP),
      c(1.0, 0.70, 0.55))

# --- regions and the section filter ----------------------------------------
rmap <- c(ALLEGHENY = "Northeast", MICHIGAN = "Midwest",
          SOUTHWESTERN = "South", CALIFORNIA = "West")
regions <- c("Northeast", "Midwest", "South", "West", "Other")
hay <- c("ALLEGHENY (Northeast)", "MICHIGAN (Midwest)",
         "SOUTHWESTERN (South)", "CALIFORNIA (West)", "MYSTERY (Other)")

check("region_of known", region_of("MICHIGAN", rmap), "Midwest")
check("region_of unknown", region_of("MYSTERY", rmap), "Other")

choices <- grouped_section_choices(c("MICHIGAN", "ALLEGHENY", "SOUTHWESTERN", "CALIFORNIA"), rmap)
check("choices order", names(choices), c("All", "Regions", "Northeast", "Midwest", "South", "West"))
check("regions group values", unlist(choices[["Regions"]], use.names = FALSE),
      c("Northeast", "Midwest", "South", "West"))
check("regions group labels", names(choices[["Regions"]]),
      c("All of Northeast", "All of Midwest", "All of South", "All of West"))
check("group members", unlist(choices[["West"]], use.names = FALSE), "CALIFORNIA")

check("filter blank", section_filter_mask("", regions, hay), rep(TRUE, 5))
check("filter all", section_filter_mask("All", regions, hay), rep(TRUE, 5))
check("filter region exact west", section_filter_mask("west", regions, hay),
      c(FALSE, FALSE, FALSE, TRUE, FALSE))
check("filter region exact south no leak", section_filter_mask("South", regions, hay),
      c(FALSE, FALSE, TRUE, FALSE, FALSE))
check("filter section word", section_filter_mask("southwestern", regions, hay),
      c(FALSE, FALSE, TRUE, FALSE, FALSE))
check("filter prefix", section_filter_mask("mic", regions, hay),
      c(FALSE, TRUE, FALSE, FALSE, FALSE))
check("filter two terms", section_filter_mask("michigan midwest", regions, hay),
      c(FALSE, TRUE, FALSE, FALSE, FALSE))
check("filter no match", section_filter_mask("michigan west", regions, hay),
      rep(FALSE, 5))
check("filter regex metachars literal", section_filter_mask("m.i", regions, hay),
      rep(FALSE, 5))

# --- speaker tags ------------------------------------------------------------
sl <- speaker_lines("Jane Smith, John Doe (Polya), Ada (Nam)")
check("speaker count", length(sl), 3L)
check("speaker no tag color", sl[[1]]$color, NULL)
check("speaker polya color", sl[[2]]$color, "#9467bd")
check("speaker keeps full name", sl[[2]]$name, "John Doe (Polya)")
check("speaker nam color", sl[[3]]$color, "#d62728")
check("speaker unknown tag", speaker_lines("Bo (Chair)")[[1]]$color, NULL)
check("speaker empty", length(speaker_lines("")), 0L)

# --- collected_line ----------------------------------------------------------
tmp <- tempfile()
writeLines("2026-10-04", tmp)
check("collected line", collected_line(tmp), "Data collected: Oct 4, 2026")
writeLines("not-a-date", tmp)
check("collected garbage", collected_line(tmp), NULL)
check("collected missing", collected_line(file.path(tempdir(), "nope.txt")), NULL)
unlink(tmp)

if (failures > 0) {
  stop("selftest failed: ", failures, " failure(s)")
}
cat("selftest OK\n")
