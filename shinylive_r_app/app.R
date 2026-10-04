# PoC: minimal R twin of the MAA sectional meetings app.
# Gate: does leaflet render through webR in a shinylive export?
library(shiny)
library(bslib)
library(leaflet)

meetings <- read.csv("data/meetings_latest.csv", stringsAsFactors = FALSE)
sections <- sort(unique(meetings$section))
choices <- c("All", sections)

ui <- page_sidebar(
  title = "MAA Sectional Meetings",
  sidebar = sidebar(
    selectizeInput(
      "section",
      "Section",
      choices = choices,
      selected = "All",
      options = list(create = TRUE)
    )
  ),
  leafletOutput("map", height = "80vh")
)

server <- function(input, output, session) {
  rows <- reactive({
    if (isTruthy(input$section) && input$section != "All" && input$section %in% sections) {
      meetings[meetings$section == input$section, , drop = FALSE]
    } else {
      meetings
    }
  })

  output$map <- renderLeaflet({
    leaflet(rows()) |>
      addTiles(group = "Standard") |>
      addProviderTiles(providers$Esri.WorldImagery, group = "Satellite") |>
      hideGroup("Satellite") |>
      addLayersControl(
        baseGroups = c("Standard", "Satellite"),
        options = layersControlOptions(collapsed = FALSE),
        position = "bottomright"
      ) |>
      addMarkers(~longitude, ~latitude, label = ~location)
  })
}

shinyApp(ui, server)
