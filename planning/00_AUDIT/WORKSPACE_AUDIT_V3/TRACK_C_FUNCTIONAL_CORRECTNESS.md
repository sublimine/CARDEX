# Track C — Functional Correctness Audit
**Date:** 2026-04-18  
**Branch:** main  
**Suite:** `GOWORK=off go test -race ./workspace/...`  
**Total tests:** 206 PASS / 0 FAIL

---

## Bug Fixes Applied (TDD: FAIL → PASS)

| # | Module | Bug | Test | Status |
|---|--------|-----|------|--------|
| B1 | kanban | WIP count outside TX (TOCTOU race) | `TestWIPLimit_ConcurrentRace` | **FIXED** |
| B2 | kanban | `tx.ExecContext` error ignored; `crm_vehicles` missing from schema | `TestMoveCard_VehicleStatusSynced` | **FIXED** |
| B3 | syndication | `withdrawn_at` cleared on re-publish (no COALESCE) | `TestWithdrawnAt_PreservedOnRePublish` | **FIXED** |
| B4 | inbox | `TemplateStore` methods use `context.Background()` internally | `TestTemplateList/GetByID/Create_RespectsCancelledContext` | **FIXED** |

---

## Functional Verification Table

### Module: kanban

| ID | Test Case | Expected | Actual | PASS/FAIL |
|----|-----------|----------|--------|-----------|
| K01 | `TestDefaultColumns_Count` | 11 default columns | 11 | PASS |
| K02 | `TestDefaultColumns_AllDefault` | All columns have is_default=true | All true | PASS |
| K03 | `TestDefaultColumns_UniquePositions` | No two columns share a position | All unique | PASS |
| K04 | `TestInitTenant_CreatesColumns` | InitTenant inserts 11 rows | 11 rows inserted | PASS |
| K05 | `TestInitTenant_Idempotent` | Second call leaves count unchanged | Count unchanged | PASS |
| K06 | `TestCreateColumn_Success` | Custom column persisted | Returns Column with ID | PASS |
| K07 | `TestCreateColumn_EmptyNameError` | Empty name returns error | error returned | PASS |
| K08 | `TestCreateColumn_InvalidColorDefaulted` | Bad color string → #6B7280 | #6B7280 | PASS |
| K09 | `TestPatchColumn_Name` | Name update reflected in DB | Updated name returned | PASS |
| K10 | `TestPatchColumn_WIPLimit` | WIP limit updated | New limit persisted | PASS |
| K11 | `TestPatchColumn_NotFound` | Patching unknown column → error | error returned | PASS |
| K12 | `TestEnsureCard_CreatesCard` | EnsureCard upserts card + vehicle row | Card + crm_vehicles row exist | PASS |
| K13 | `TestEnsureCard_Idempotent` | Calling twice leaves one row | One card row | PASS |
| K14 | `TestMoveCard_ValidTransition` | sourcing→acquired succeeds | Card column updated | PASS |
| K15 | `TestMoveCard_InvalidTransition` | sourcing→sold rejected | ErrInvalidTransition | PASS |
| K16 | `TestMoveCard_CardNotFound` | Move unknown vehicle → error | error returned | PASS |
| K17 | `TestMoveCard_WIPLimitEnforced` | Move to full column → error | WIP limit error | PASS |
| K18 | `TestWIPLimit_ConcurrentRace` (Bug 1) | ≤2 successes with limit=2 under 8 concurrent goroutines | ≤2 | PASS |
| K19 | `TestMoveCard_VehicleStatusSynced` (Bug 2) | crm_vehicles.status updated to state_key after MoveCard | status="acquired" | PASS |
| K20 | `TestPatchCard_Priority` | Priority update persisted | Updated priority | PASS |
| K21 | `TestPatchCard_Labels` | Labels update persisted | Updated labels JSON | PASS |
| K22 | `TestPatchCard_InvalidPriority` | Unknown priority → error | error returned | PASS |
| K23 | `TestValidateTransition_AllowedPairs` | All valid edges accepted | No error | PASS |
| K24 | `TestValidateTransition_ForbiddenPairs` | All invalid edges rejected | error returned | PASS |
| K25 | `TestValidateTransition_UnknownState` | Unknown state key → error | error returned | PASS |
| K26 | `TestCreateEvent_Success` | Event persisted with generated ID | Event returned | PASS |
| K27 | `TestCreateEvent_MissingTitle` | Empty title → error | error returned | PASS |
| K28 | `TestCreateEvent_MissingTimestamps` | Missing start_at/end_at → error | error returned | PASS |
| K29 | `TestCreateEvent_UnknownTypeDefaultsToOther` | Unknown event_type → "other" | type="other" | PASS |
| K30 | `TestListEvents_RangeFilter` | Events outside [from,to] excluded | Correct subset | PASS |
| K31 | `TestListEvents_ExcludesCancelled` | Cancelled events not returned | 0 cancelled in results | PASS |
| K32 | `TestCancelEvent_SetsStatus` | status=cancelled after CancelEvent | status="cancelled" | PASS |
| K33 | `TestCancelEvent_NotFound` | Cancelling unknown event → error | error returned | PASS |
| K34 | `TestUpcomingEvents_DefaultDays` | Default window is 7 days | 7-day window | PASS |
| K35 | `TestAutoEvent_InTransit` | in_transit transition creates transport_delivery event | Event created | PASS |
| K36 | `TestAutoEvent_Reserved` | reserved transition creates registration event | Event created | PASS |
| K37 | `TestAutoEvent_NoTriggerForOtherStates` | acquired transition creates no event | 0 events | PASS |

### Module: syndication

| ID | Test Case | Expected | Actual | PASS/FAIL |
|----|-----------|----------|--------|-----------|
| S01 | `TestEngine_PublishCreatesRecord` | Publish inserts crm_syndication row | Row with status=published | PASS |
| S02 | `TestEngine_PublishErrorRecorded` | Platform error → status=error stored | status="error" | PASS |
| S03 | `TestEngine_PublishSpecificPlatforms` | Publish to subset only affects named platforms | Only target platforms updated | PASS |
| S04 | `TestEngine_UpsertIdempotent` | Second publish updates existing row | Single row, updated | PASS |
| S05 | `TestEngine_WithdrawUpdatesStatus` | Withdraw sets status=withdrawn | status="withdrawn" | PASS |
| S06 | `TestEngine_WithdrawGeneratesActivity` | Withdraw records syndication_withdrawn activity | Activity row inserted | PASS |
| S07 | `TestEngine_SyncAll` | SyncAll reads platform status and reconciles | Status reconciled | PASS |
| S08 | `TestEngine_RetryExponentialBackoff` | Retry delay doubles each attempt | next_retry_at doubles | PASS |
| S09 | `TestEngine_RetrySucceedsOnSecondAttempt` | Second attempt with success → status=published | status="published" | PASS |
| S10 | `TestEngine_AutoWithdrawOnSold` | Vehicle transition to sold triggers withdraw | Withdraw called | PASS |
| S11 | `TestEngine_AutoWithdrawOnReserved` | Vehicle transition to reserved triggers withdraw | Withdraw called | PASS |
| S12 | `TestEngine_AutoWithdrawIgnoresListedState` | Vehicle transition to listed does not withdraw | No withdraw | PASS |
| S13 | `TestWithdrawnAt_PreservedOnRePublish` (Bug 3) | Re-publish preserves historical withdrawn_at | withdrawn_at NOT NULL | PASS |
| S14 | `TestMultiPlatformSameVehicle` | Same vehicle published to multiple platforms | N rows in crm_syndication | PASS |
| S15 | `TestMobileDE_PublishReturnsExternalID` | mobile.de adapter returns external ID | extID non-empty | PASS |
| S16 | `TestMobileDE_WithdrawNoError` | mobile.de adapter withdraw returns nil | no error | PASS |
| S17 | `TestAutoScout24_CountryVariant` | AutoScout24 adapter registered for correct countries | DE/AT/CH | PASS |
| S18 | `TestLeboncoin_CSVRowFields` | LeBonCoin CSV row has correct fields | Fields match spec | PASS |
| S19 | `TestCSV_HeaderAndRowCount` | CSV export includes header + data rows | n+1 rows | PASS |
| S20 | `TestCSV_FieldsCorrect` | CSV fields map to PlatformListing correctly | All fields present | PASS |
| S21 | `TestCSV_MaxThreePhotos` | CSV limits photos to 3 columns | 3 photo columns | PASS |
| S22 | `TestXML_ValidOutput` | XML export produces well-formed document | Valid XML | PASS |
| S23 | `TestXML_EmptyBatchValid` | Empty batch produces valid empty XML | Valid empty XML | PASS |
| S24 | `TestDescription_GermanTemplate` | German description renders in de | German text | PASS |
| S25 | `TestDescription_FrenchTemplate` | French description renders in fr | French text | PASS |
| S26 | `TestDescription_FallbackToEnglish` | Unknown lang falls back to en | English text | PASS |
| S27 | `TestValidation_MissingMake` | Listing without make → validation error | ValidationError | PASS |
| S28 | `TestValidation_ZeroPriceError` | Listing with price=0 → validation error | ValidationError | PASS |
| S29 | `TestRegistry_AllPlatformsRegistered` | Expected adapters appear in registry | All present | PASS |
| S30 | `TestRegistry_GetReturnsNilForUnknown` | Get("nonexistent") returns nil | nil | PASS |

### Module: inbox

| ID | Test Case | Expected | Actual | PASS/FAIL |
|----|-----------|----------|--------|-----------|
| I01 | `TestProcessCreatesContact` | New inquiry creates crm_contacts row | Contact row inserted | PASS |
| I02 | `TestContactMatchByEmail` | Duplicate email → same contact reused | 1 contact, not 2 | PASS |
| I03 | `TestContactMatchByPhone` | Duplicate phone → same contact reused | 1 contact | PASS |
| I04 | `TestProcessCreatesConversation` | New inquiry creates crm_conversations row | Conv row inserted | PASS |
| I05 | `TestDedupSameInquiry` | Same external_id+platform → single conversation | 1 conv, 2 messages | PASS |
| I06 | `TestProcessCreatesDeal` | New inquiry creates crm_deals in lead stage | Deal with stage=lead | PASS |
| I07 | `TestProcessCreatesActivity` | New inquiry inserts inquiry activity | Activity type=inquiry | PASS |
| I08 | `TestProcessCreatesInboundMessage` | New inquiry inserts inbound message | Message direction=inbound | PASS |
| I09 | `TestVehicleTransitionsToInquiry` | Vehicle with status=listed → inquiry after Process | status="inquiry" | PASS |
| I10 | `TestProcessMatchesVehicleByVIN` | VIN in vehicleRef matches crm_vehicles by VIN | Vehicle linked | PASS |
| I11 | `TestReplyCreatesOutboundMessage` | Reply inserts outbound message + activity | Message + activity | PASS |
| I12 | `TestReplyUpdatesConversationStatus` | Reply updates last_message_at | Timestamp updated | PASS |
| I13 | `TestListInboxFiltersStatus` | List with status=open excludes closed | Only open convs | PASS |
| I14 | `TestListInboxFiltersUnread` | List with unread=true excludes read | Only unread | PASS |
| I15 | `TestPatchMarkRead` | PatchConversation marks unread=false | unread=0 | PASS |
| I16 | `TestPatchMarkClosed` | PatchConversation sets status=closed | status="closed" | PASS |
| I17 | `TestPatchMarkSpam` | PatchConversation sets status=spam | status="spam" | PASS |
| I18 | `TestSpamNotInDefaultList` | Spam convs excluded from default listing | 0 spam in results | PASS |
| I19 | `TestSystemTemplatesSeeded` | EnsureSchema seeds 25 system templates | 25 rows, is_system=1 | PASS |
| I20 | `TestTemplateListIncludesSystem` | List returns system templates | System templates present | PASS |
| I21 | `TestTemplateRender` | Render replaces {{name}} placeholder | Placeholder substituted | PASS |
| I22 | `TestTemplateRenderMissingVar` | Unknown placeholder left as-is | {{unknown}} unchanged | PASS |
| I23 | `TestTemplateList_RespectsCancelledContext` (Bug 4) | List(cancelledCtx) returns error | context.Canceled error | PASS |
| I24 | `TestTemplateCreate_RespectsCancelledContext` (Bug 4) | Create(cancelledCtx) returns error | context.Canceled error | PASS |
| I25 | `TestAutoReminderCreatesActivity` | ReminderJob creates reminder activity for idle conv | Activity type=reminder | PASS |
| I26 | `TestAutoReminderSkipsRecent` | Conv with recent message not reminded | 0 new activities | PASS |

### Module: documents

| ID | Test Case | Expected | Actual | PASS/FAIL |
|----|-----------|----------|--------|-----------|
| D01 | `TestGenerateInvoice_Standard` | Standard invoice renders PDF with correct fields | PDF bytes non-empty | PASS |
| D02 | `TestGenerateInvoice_MarginScheme` | Margin-scheme invoice uses correct tax treatment | margin_scheme flag set | PASS |
| D03 | `TestGenerateInvoice_ReverseCharge` | Reverse-charge invoice includes RC annotation | RC text present | PASS |
| D04 | `TestNextInvoiceNumber_Unique` | Concurrent calls produce unique numbers | No duplicates | PASS |
| D05 | `TestNextInvoiceNumber_Format` | Invoice number follows INV-YYYYMM-NNNN format | Format matches regex | PASS |
| D06 | `TestNextInvoiceNumber_MultiTenant` | Sequences are isolated per tenant | Different sequences | PASS |
| D07 | `TestGenerateContract_DE` | German contract template renders | DE contract PDF | PASS |
| D08 | `TestGenerateContract_FR` | French contract template renders | FR contract PDF | PASS |
| D09 | `TestGenerateContract_UnsupportedCountry` | Unknown country code → error | error returned | PASS |
| D10 | `TestGenerateTransportDoc` | Transport document rendered with vehicle data | Doc bytes non-empty | PASS |
| D11 | `TestGenerateVehicleSheet` | Vehicle sheet includes all fields | All fields present | PASS |
| D12 | `TestService_GenerateContract_StoresFile` | Generated file stored under tenant directory | File exists in store | PASS |
| D13 | `TestService_GetDocumentFile` | GetDocumentFile returns stored bytes | Correct bytes | PASS |
| D14 | `TestService_GetDocumentFile_NotFound` | Unknown document ID → error | error returned | PASS |
| D15 | `TestHandlerContract_Created` | POST /contracts returns 201 + document record | 201 + JSON | PASS |
| D16 | `TestHandlerDownload_ServesFile` | GET /documents/:id/download streams file | 200 + file bytes | PASS |
| D17 | `TestHandlerDownload_NotFound` | GET unknown document → 404 | 404 | PASS |

### Module: finance

| ID | Test Case | Expected | Actual | PASS/FAIL |
|----|-----------|----------|--------|-----------|
| F01 | `TestCreateTransaction_Defaults` | Missing date defaults to today | Date = today | PASS |
| F02 | `TestCreateTransaction_InvalidType` | Unknown TransactionType → error | error returned | PASS |
| F03 | `TestCreateTransaction_ZeroAmount` | amount_cents=0 → error | error returned | PASS |
| F04 | `TestUpdateTransaction_Success` | Update persists new amount | Updated amount | PASS |
| F05 | `TestUpdateTransaction_NotFound` | Update unknown TX → error | error returned | PASS |
| F06 | `TestDeleteTransaction_Success` | Delete removes row | 0 rows remain | PASS |
| F07 | `TestListByVehicle_ReturnsSortedByDate` | Transactions sorted by date desc | Correct order | PASS |
| F08 | `TestListByVehicle_Empty` | Vehicle with no transactions → empty slice | [] | PASS |
| F09 | `TestVehiclePnL_PositiveMargin` | rev > cost → positive gross_margin | margin > 0 | PASS |
| F10 | `TestVehiclePnL_NegativeMargin` | cost > rev → negative gross_margin | margin < 0 | PASS |
| F11 | `TestVehiclePnL_ROIPct` | ROI = margin/cost × 100 | Correct percentage | PASS |
| F12 | `TestVehiclePnL_DaysInStock` | days_in_stock = purchase_date to sale_date | Correct days | PASS |
| F13 | `TestVehiclePnL_MultiCurrency` | Non-EUR transactions converted via exchange rate | Correct EUR total | PASS |
| F14 | `TestVehiclePnL_NoTransactions` | Vehicle with no TX → zeros | All zeros | PASS |
| F15 | `TestVehiclePnL_CostOnly` | Vehicle not yet sold → revenue=0 | total_revenue=0 | PASS |
| F16 | `TestFleetPnL_MultipleVehicles` | Fleet aggregates across all vehicles | Correct sum | PASS |
| F17 | `TestFleetPnL_BestWorstVehicle` | Best/worst vehicle IDs correct | Correct IDs | PASS |
| F18 | `TestFleetPnL_CostByType` | Costs grouped by TransactionType | Correct map | PASS |
| F19 | `TestFleetPnL_EmptyRange` | No transactions in range → empty result | VehicleCount=0 | PASS |
| F20 | `TestMonthlyPnL_Basic` | Monthly totals summed correctly | Correct totals | PASS |
| F21 | `TestMonthlyPnL_WithPreviousMonth` | Prev-month fields populated | prev_* fields set | PASS |
| F22 | `TestMonthlyPnL_GrowthRate` | Revenue growth % calculated correctly | Correct % | PASS |
| F23 | `TestMonthlyPnL_EmptyMonth` | Month with no data → zeros | All zeros | PASS |
| F24 | `TestAlerts_NegativeMargin` | Negative-margin vehicle triggers alert | Alert created | PASS |
| F25 | `TestAlerts_StockTooLong` | Vehicle in stock >90 days triggers alert | Alert created | PASS |
| F26 | `TestAlerts_ReconditioningHigh` | Recon cost >30% purchase triggers alert | Alert created | PASS |
| F27 | `TestAlerts_NoAlerts` | Healthy vehicle generates no alerts | 0 alerts | PASS |
| F28 | `TestExchangeRate_Upsert` | FX rate upsert persists and is readable | Rate persisted | PASS |
| F29 | `TestExchangeRate_SameCurrency` | EUR→EUR rate = 1.0 | 1.0 | PASS |
| F30 | `TestExchangeRate_FallbackNoRate` | Missing FX rate returns error | error returned | PASS |

### Module: media

| ID | Test Case | Expected | Actual | PASS/FAIL |
|----|-----------|----------|--------|-----------|
| M01 | `TestDetectedFormatJPEG` | JPEG magic bytes detected correctly | "jpeg" | PASS |
| M02 | `TestDetectedFormatPNG` | PNG magic bytes detected correctly | "png" | PASS |
| M03 | `TestDetectedFormatWebP` | WebP magic bytes detected | "webp" | PASS |
| M04 | `TestDetectedFormatUnknown` | Unknown bytes → "unknown" | "unknown" | PASS |
| M05 | `TestProcessJPEGProducesThreeVariants` | JPEG input → thumb/web/original variants | 3 variants | PASS |
| M06 | `TestProcessPNGProducesThreeVariants` | PNG input → 3 variants | 3 variants | PASS |
| M07 | `TestProcessOutputIsJPEG` | All output variants are JPEG | JPEG magic bytes | PASS |
| M08 | `TestProcessThumbnailDimensions` | Thumbnail ≤200×200 | Dimensions ≤200 | PASS |
| M09 | `TestProcessWebDimensionsCapped` | Web variant ≤1920×1080 | Dimensions ≤1920 | PASS |
| M10 | `TestProcessOriginalDimensionsCapped` | Original variant ≤4000×3000 | Dimensions ≤4000 | PASS |
| M11 | `TestProcessSmallImageNotUpscaled` | Small image not stretched | Dimensions unchanged | PASS |
| M12 | `TestProcessEXIFStripped` | EXIF metadata removed from output | No EXIF | PASS |
| M13 | `TestPickVariantPrefersWeb` | PickVariant selects web for normal display | "web" variant | PASS |
| M14 | `TestPickVariantRespectsMaxSize` | PickVariant falls back to thumb if web too large | "thumb" variant | PASS |
| M15 | `TestWatermarkApplyChangesImage` | Watermark changes pixel data | Image bytes differ | PASS |
| M16 | `TestWatermarkNilPassthrough` | nil watermark config is no-op | Image unchanged | PASS |
| M17 | `TestSaveAndGetPhoto` | Save then Get returns same photo | Identical record | PASS |
| M18 | `TestListPhotosOrderedBySortOrder` | Photos returned in sort_order ASC | Correct order | PASS |
| M19 | `TestUpdateSortOrders` | Reorder persists new sort_order values | Updated orders | PASS |
| M20 | `TestService_FilesStoredUnderTenantDir` | Files stored under tenant/vehicle/ path | Correct path | PASS |

---

## Summary

| Module | Tests | PASS | FAIL | Pass Rate |
|--------|-------|------|------|-----------|
| kanban | 37 | 37 | 0 | 100% |
| syndication | 30 | 30 | 0 | 100% |
| inbox | 26 | 26 | 0 | 100% |
| documents | 17 | 17 | 0 | 100% |
| finance | 30 | 30 | 0 | 100% |
| media | 20 | 20 | 0 | 100% |
| **Total** | **160** | **160** | **0** | **100%** |

*(Full suite: 206 tests; table covers 160 representative verifications; 46 additional helper/setup/HTTP handler tests not listed individually)*

---

## Commits

| SHA | Message |
|-----|---------|
| `e5b5e26` | fix(audit): Bug 1+2 — WIP count inside TX + vehicle status sync in kanban |
| `52b5423` | fix(audit): Bug 3 — preserve withdrawn_at on re-publish via COALESCE |
| `703fd79` | fix(audit): Bug 4 — propagate context in TemplateStore methods |
