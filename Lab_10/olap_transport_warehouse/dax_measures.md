# Power BI DAX Specification

Create the following measures after importing the five clean CSV files.

## 1. Base measures

```DAX
Total Vehicle Volume =
SUM(fact_traffic_observations[VehicleCount])
```

```DAX
Total Passengers =
SUM(fact_traffic_observations[PassengerCount])
```

```DAX
Average Observed Speed =
AVERAGE(fact_traffic_observations[ObservedSpeed])
```

```DAX
Average Delay (min) =
AVERAGE(fact_traffic_observations[DelayMinutes])
```

```DAX
Total Incidents =
SUM(fact_traffic_observations[IncidentFlag])
```

## 2. Supporting measures

```DAX
Average Allowed Speed =
AVERAGEX(
    fact_traffic_observations,
    RELATED(dim_road_segment[AllowedSpeed])
)
```

```DAX
High Congestion Observations =
SUM(fact_traffic_observations[CongestionAlertFlag])
```

## 3. Speed deficit

This measures the percentage by which observed speed is below the allowed speed.

```DAX
Speed Deficit % =
VAR Allowed = [Average Allowed Speed]
VAR Observed = [Average Observed Speed]
RETURN
    IF(
        ISBLANK(Observed) || Allowed <= 0,
        BLANK(),
        MAX(0, DIVIDE(Allowed - Observed, Allowed))
    )
```

Format as **Percentage**.

## 4. Public transit share

This is the share of vehicle volume attributable to Bus/Tram within the current report context.

```DAX
Public Transit Share % =
VAR TransitVolume =
    CALCULATE(
        [Total Vehicle Volume],
        KEEPFILTERS(
            dim_transport_route[TransportType] IN { "Bus", "Tram" }
        )
    )
RETURN
    DIVIDE(TransitVolume, [Total Vehicle Volume])
```

Format as **Percentage**.

## 5. Volume % of total

The required comparison removes only the road-segment filter.

```DAX
Volume % of Total =
DIVIDE(
    [Total Vehicle Volume],
    CALCULATE(
        [Total Vehicle Volume],
        ALL(dim_road_segment)
    )
)
```

Format as **Percentage**.

For a report-wide modal share independent of route selection, use this additional measure:

```DAX
Volume % of Grand Total =
DIVIDE(
    [Total Vehicle Volume],
    CALCULATE(
        [Total Vehicle Volume],
        REMOVEFILTERS(dim_road_segment),
        REMOVEFILTERS(dim_transport_route),
        REMOVEFILTERS(dim_transport_event)
    )
)
```

## 6. Incident speed comparison

Normal Flow average speed:

```DAX
Normal Flow Average Speed =
CALCULATE(
    [Average Observed Speed],
    dim_transport_event[EventType] = "Normal Flow"
)
```

Incident average speed:

```DAX
Incident Average Speed =
CALCULATE(
    [Average Observed Speed],
    dim_transport_event[EventType] <> "Normal Flow"
)
```

Speed drop during incidents:

```DAX
Speed Drop during Incidents % =
VAR NormalSpeed = [Normal Flow Average Speed]
VAR IncidentSpeed = [Incident Average Speed]
RETURN
    IF(
        ISBLANK(NormalSpeed) || NormalSpeed = 0,
        BLANK(),
        DIVIDE(NormalSpeed - IncidentSpeed, NormalSpeed)
    )
```

Format as **Percentage**.

## 7. RuleHighCongestion activations

```DAX
High Congestion Rule Triggers Count =
CALCULATE(
    COUNTROWS(fact_traffic_observations),
    dim_transport_event[DecisionRule] = "RuleHighCongestion"
)
```

This counts fact observations associated with the rule, which is the appropriate interpretation for the synthetic warehouse's event grain.

## 8. Peak-hour measures

```DAX
Peak Hour Vehicle Volume =
CALCULATE(
    [Total Vehicle Volume],
    dim_date[IsPeakHour] = TRUE()
)
```

```DAX
Peak Hour Average Speed =
CALCULATE(
    [Average Observed Speed],
    dim_date[IsPeakHour] = TRUE()
)
```

## 9. YoY measures

```DAX
Vehicle Volume YoY =
CALCULATE(
    [Total Vehicle Volume],
    DATEADD(dim_date[FullDate], -1, YEAR)
)
```

```DAX
Vehicle Volume YoY Change =
[Total Vehicle Volume] - [Vehicle Volume YoY]
```

```DAX
Vehicle Volume YoY % =
DIVIDE(
    [Vehicle Volume YoY Change],
    [Vehicle Volume YoY]
)
```

Note: the synthetic dataset covers only 2026, so a YoY value is expected to be blank unless the model is later extended with prior-year data. The measure is supplied to make the model ready for a multi-year warehouse.

## 10. Month-over-month incident analysis

```DAX
Incidents Previous Month =
CALCULATE(
    [Total Incidents],
    DATEADD(dim_date[FullDate], -1, MONTH)
)
```

```DAX
Incidents MoM Change =
[Total Incidents] - [Incidents Previous Month]
```

```DAX
Incidents MoM % =
DIVIDE(
    [Incidents MoM Change],
    [Incidents Previous Month]
)
```

## 11. Congestion rate

```DAX
Congestion Alert Rate % =
DIVIDE(
    [High Congestion Observations],
    COUNTROWS(fact_traffic_observations)
)
```

Format as **Percentage**.

## 12. Report-level validation

After creating measures, place these on a temporary card/table:

- Total Vehicle Volume
- Total Passengers
- Average Observed Speed
- Average Delay (min)
- Total Incidents
- Speed Deficit %
- Public Transit Share %
- Volume % of Total
- Speed Drop during Incidents %
- High Congestion Rule Triggers Count

Then slice the page by:

- District
- TransportType
- EventType
- IsPeakHour

The measures should respond to dimension filters without requiring bidirectional relationships.
