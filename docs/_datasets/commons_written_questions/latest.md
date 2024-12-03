---
name: commons_written_questions
title: Commons Written Questions
description: "Dataset of Parliamentary written question since 2023-09\n"
version: latest
licenses:
- name: CC-BY-4.0
  path: https://creativecommons.org/licenses/by/4.0/
  title: Creative Commons Attribution 4.0 International License
contributors:
- title: mySociety
  path: https://mysociety.org
  role: author
- title: UK Parliament
  path: https://www.parliament.uk/
  role: author
custom:
  build: uk_parl_written_questions.fetch:create_dataset
  tests:
  - test_commons_written_questions
  dataset_order: 0
  download_options:
    gate: default
    survey: default
    header_text: default
  formats:
    csv: true
    parquet: true
    gpkg: false
    geojson: false
  is_geodata: false
  composite:
    xlsx:
      include: all
      exclude: none
      render: false
    sqlite:
      include: all
      exclude: none
      render: true
    json:
      include: all
      exclude: none
      render: false
  change_log:
    0.1.0: 'Change in data for resource(s): written_questions'
  datasette:
    about: Info & Downloads
    about_url: https://pages.mysociety.org/uk_parl_written_questions/datasets/commons_written_questions/0_1_0
resources:
- title: Written question
  description: Republishing WQs since 2023-09
  custom:
    row_count: 54042
    datasette:
      about: Info & Downloads
      about_url: https://pages.mysociety.org/uk_parl_written_questions/datasets/commons_written_questions/0_1_0#written_questions
  path: written_questions.parquet
  name: written_questions
  profile: data-resource
  scheme: file
  format: parquet
  hashing: md5
  encoding: utf-8
  schema:
    fields:
    - name: id
      type: integer
      description: Internal Parliament ID for question
      constraints:
        unique: true
      example: '1655762'
    - name: askingMemberId
      type: integer
      description: MINS ID of the MP asking the question
      constraints:
        unique: false
      example: '14'
    - name: askingMember
      type: string
      description: Name of the MP asking the question
      constraints:
        unique: false
      example: ''
    - name: house
      type: string
      description: House of Parliament the question was asked in
      constraints:
        unique: false
        enum:
        - Commons
      example: Commons
    - name: memberHasInterest
      type: boolean
      description: Whether the MP asking the question has declared an interest
      constraints:
        unique: false
        enum:
        - false
        - true
      example: 'False'
    - name: dateTabled
      type: string
      description: Date the question was tabled
      constraints:
        unique: false
      example: '2023-09-01T00:00:00'
    - name: dateForAnswer
      type: string
      description: Date the question is due for answer
      constraints:
        unique: false
      example: '2023-09-05T00:00:00'
    - name: uin
      type: string
      description: Unique ID for the question (in combo with date)
      constraints:
        unique: false
      example: '1'
    - name: questionText
      type: string
      description: The text of the question
      constraints:
        unique: false
      example: How many and what proportion of households have applied to the Great
        British Insulation Scheme.
    - name: answeringBodyId
      type: integer
      description: MINS ID of the department answering the question
      constraints:
        unique: false
      example: '1'
    - name: answeringBodyName
      type: string
      description: Name of the department answering the question
      constraints:
        unique: false
      example: Attorney General
    - name: isWithdrawn
      type: boolean
      description: Whether the question has been withdrawn
      constraints:
        unique: false
        enum:
        - false
      example: 'False'
    - name: isNamedDay
      type: boolean
      description: Whether the question is a named day question
      constraints:
        unique: false
        enum:
        - false
        - true
      example: 'False'
    - name: groupedQuestions
      type: string
      description: List of questions grouped together
      constraints:
        unique: false
      example: '[]'
    - name: answerIsHolding
      type: string
      description: Whether the answer is a holding answer
      constraints:
        unique: false
      example: 'False'
    - name: answerIsCorrection
      type: string
      description: Whether the answer is a correction
      constraints:
        unique: false
      example: 'False'
    - name: answeringMemberId
      type: number
      description: MINS ID of the MP answering the question
      constraints:
        unique: false
      example: '39.0'
    - name: answeringMember
      type: string
      description: Name of the MP answering the question
      constraints:
        unique: false
      example: ''
    - name: correctingMemberId
      type: number
      description: MINS ID of the MP correcting the answer
      constraints:
        unique: false
      example: '39.0'
    - name: correctingMember
      type: string
      description: Name of the MP correcting the answer
      constraints:
        unique: false
      example: ''
    - name: dateAnswered
      type: string
      description: Date the question was answered
      constraints:
        unique: false
      example: '2023-09-05T00:00:00'
    - name: answerText
      type: string
      description: The text of the answer
      constraints:
        unique: false
      example: '         Information relating to children and young people was not
        collected prior to 2016/17. The following table shows the number of referrals
        received in Cumberland and Westmorland and Furness local authorities between
        2016/17 and 2022/23, the latest p...'
    - name: originalAnswerText
      type: string
      description: The original text of the answer
      constraints:
        unique: false
        enum:
        - ''
      example: ''
    - name: comparableAnswerText
      type: string
      description: The text of the answer, with all whitespace removed
      constraints:
        unique: false
        enum:
        - ''
      example: ''
    - name: dateAnswerCorrected
      type: string
      description: Date the answer was corrected
      constraints:
        unique: false
      example: '2023-09-12T00:00:00'
    - name: dateHoldingAnswer
      type: string
      description: Date the holding answer was given
      constraints:
        unique: false
      example: '2023-09-06T00:00:00'
    - name: attachmentCount
      type: integer
      description: Number of attachments to the answer
      constraints:
        unique: false
        enum:
        - 0
      example: '0'
    - name: heading
      type: string
      description: The heading of the question
      constraints:
        unique: false
      example: ' MOD St Athan'
    - name: attachments
      type: string
      description: List of attachments to the answer
      constraints:
        unique: false
      example: '[]'
    - name: groupedQuestionsDates
      type: string
      description: List of dates for grouped questions
      constraints:
        unique: false
      example: '[]'
    - name: twfy_id
      type: string
      description: TheyWorkForYou ID of the MP asking the question
      constraints:
        unique: false
      example: '10001'
    - name: person_name
      type: string
      description: Name of the MP asking the question
      constraints:
        unique: false
      example: Abena Oppong-Asare
    - name: url
      type: string
      description: URL of the question on the Parliament website
      constraints:
        unique: true
      example: https://questions-statements.parliament.uk/written-questions/detail/2023-09-01/195613/
  hash: a827982a7d560b660504c5e6c07b503e
full_version: 0.1.0
permalink: /datasets/commons_written_questions/latest
---
