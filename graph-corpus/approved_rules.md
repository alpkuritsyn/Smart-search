# Approved complement rules

## type:paint --PREPARE_WITH--> type:primer
Rationale: Подготовка основания перед окрашиванием; конкретный грунт выбирается по основанию.
Provenance: expert-rule:v1.1:01
Review status: approved

## type:paint --LEVEL_WITH--> type:putty
Rationale: Выравнивание дефектов перед окрашиванием, когда оно требуется.
Provenance: expert-rule:v1.1:02
Review status: approved

## type:paint --APPLY_WITH--> type:brush
Rationale: Один из инструментов нанесения краски.
Provenance: expert-rule:v1.1:03
Review status: approved

## type:paint --APPLY_WITH--> type:roller
Rationale: Инструмент нанесения краски на сравнительно большие площади.
Provenance: expert-rule:v1.1:04
Review status: approved

## type:primer --APPLY_WITH--> type:brush
Rationale: Один из инструментов нанесения грунтовки.
Provenance: expert-rule:v1.1:05
Review status: approved

## type:primer --APPLY_WITH--> type:roller
Rationale: Инструмент нанесения грунтовки на стены и полы.
Provenance: expert-rule:v1.1:06
Review status: approved

## type:primer --LEVEL_WITH--> type:putty
Rationale: Материал выравнивания, который может применяться в системе подготовки основания.
Provenance: expert-rule:v1.1:07
Review status: approved

## type:varnish --PREPARE_WITH--> type:primer
Rationale: Подготовка основания перед лакированием, если её требует инструкция выбранного лака.
Provenance: expert-rule:v1.1:08
Review status: approved

## type:varnish --APPLY_WITH--> type:brush
Rationale: Один из инструментов нанесения лака.
Provenance: expert-rule:v1.1:09
Review status: approved

## type:putty --PREPARE_WITH--> type:primer
Rationale: Грунтование основания перед шпаклеванием, если это предусмотрено технологией работ.
Provenance: expert-rule:v1.1:10
Review status: approved

## type:brush --USE_WITH--> type:paint
Rationale: Кисть применяется с красками подходящего состава и назначения.
Provenance: expert-rule:v1.1:11
Review status: approved

## type:brush --USE_WITH--> type:varnish
Rationale: Кисть применяется с лаками, если тип ворса допускается инструкцией покрытия.
Provenance: expert-rule:v1.1:12
Review status: approved

## type:roller --USE_WITH--> type:paint
Rationale: Валик применяется с красками при соответствии материала шубки составу покрытия.
Provenance: expert-rule:v1.1:13
Review status: approved

## type:roller --USE_WITH--> type:primer
Rationale: Валик может применяться для грунтовок на подходящих основаниях.
Provenance: expert-rule:v1.1:14
Review status: approved

## type:plaster --PREPARE_WITH--> type:primer
Rationale: Основание грунтуют перед оштукатуриванием, когда этого требует система материалов.
Provenance: expert-rule:v1.1:15
Review status: approved

## type:plaster --FINISH_WITH--> type:putty
Rationale: Шпатлевка может использоваться для финишного выравнивания оштукатуренной поверхности.
Provenance: expert-rule:v1.1:16
Review status: approved

## type:tile_glue --PREPARE_WITH--> type:primer
Rationale: Грунтовка основания перед плиточным клеем выбирается по типу основания и инструкции клея.
Provenance: expert-rule:v1.1:17
Review status: approved
