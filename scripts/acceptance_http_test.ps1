$ErrorActionPreference = "Stop"

$Base = "http://localhost:8000"

function Write-Section($Title) {
  Write-Host ""
  Write-Host "==================================================" -ForegroundColor Cyan
  Write-Host $Title -ForegroundColor Cyan
  Write-Host "==================================================" -ForegroundColor Cyan
}

function Get-JobParams($JobId) {
  $url = "$Base/api/connector-cad/jobs/$JobId/files/params.json"
  return Invoke-RestMethod $url
}

function Check-FileHead($JobId, $FileName) {
  $url = "$Base/api/connector-cad/jobs/$JobId/files/$FileName"
  try {
    $response = Invoke-WebRequest -Uri $url -Method Head
    Write-Host "$FileName -> HTTP $($response.StatusCode)" -ForegroundColor Green
  } catch {
    Write-Host "$FileName -> FAILED: $($_.Exception.Message)" -ForegroundColor Red
  }
}

Write-Section "AI STATUS"
$aiStatus = Invoke-RestMethod "$Base/api/ai/status"
$aiStatus | ConvertTo-Json -Depth 8
if (-not $aiStatus.configured) {
  Write-Host "WARNING: AI is not configured. AI-related assertions may fail." -ForegroundColor Yellow
}

Write-Section "TEST 1: 1-968970-1 should use TE_BLUE_MULTI_CAVITY series template"
$body1 = @{
  input_type = "text"
  text = "1-968970-1"
} | ConvertTo-Json -Depth 8

$job1 = Invoke-RestMethod "$Base/api/connector-cad/jobs" -Method Post -ContentType "application/json" -Body $body1
$job1 | ConvertTo-Json -Depth 10

$jobId1 = $job1.job_id
$params1 = Get-JobParams $jobId1
$params1 | ConvertTo-Json -Depth 20

Write-Host "ASSERT model_origin should be series_template:" $params1.model_origin
Write-Host "ASSERT template_name should be TE_BLUE_MULTI_CAVITY:" $params1.template_name
Write-Host "ASSERT preview color should be blue:" $params1.preview_style.base_color
Write-Host "ASSERT appearance mode:" $params1.appearance_pipeline.mode

Check-FileHead $jobId1 "model.step"
Check-FileHead $jobId1 "model.stl"
Check-FileHead $jobId1 "drawing.dxf"
Check-FileHead $jobId1 "params.json"
Check-FileHead $jobId1 "source_manifest.json"

Write-Section "TEST 2: LOCAL SAMPLE STEP should remain official_cad"
$body2 = @{
  input_type = "text"
  text = "LOCAL SAMPLE STEP"
} | ConvertTo-Json -Depth 8

$job2 = Invoke-RestMethod "$Base/api/connector-cad/jobs" -Method Post -ContentType "application/json" -Body $body2
$job2 | ConvertTo-Json -Depth 10

$jobId2 = $job2.job_id
$params2 = Get-JobParams $jobId2
$params2 | ConvertTo-Json -Depth 20

Write-Host "ASSERT model_origin should be official_cad:" $params2.model_origin
Write-Host "AI extraction status can be skipped:" $params2.ai_extraction.status

Check-FileHead $jobId2 "model.step"
Check-FileHead $jobId2 "model.stl"
Check-FileHead $jobId2 "drawing.dxf"
Check-FileHead $jobId2 "params.json"
Check-FileHead $jobId2 "source_manifest.json"

Write-Section "TEST 3: ordinary text should use AI extraction and not official_cad"
$body3 = @{
  input_type = "text"
  text = "2 pin rectangular connector pitch 6.0mm body length 36mm body width 18mm"
} | ConvertTo-Json -Depth 8

$job3 = Invoke-RestMethod "$Base/api/connector-cad/jobs" -Method Post -ContentType "application/json" -Body $body3
$job3 | ConvertTo-Json -Depth 10

$jobId3 = $job3.job_id
$params3 = Get-JobParams $jobId3
$params3 | ConvertTo-Json -Depth 20

Write-Host "ASSERT model_origin should NOT be official_cad:" $params3.model_origin
Write-Host "ASSERT AI extraction status should be success:" $params3.ai_extraction.status
Write-Host "AI extracted:" ($params3.ai_extraction.extracted | ConvertTo-Json -Depth 10)

Check-FileHead $jobId3 "model.step"
Check-FileHead $jobId3 "model.stl"
Check-FileHead $jobId3 "drawing.dxf"
Check-FileHead $jobId3 "params.json"
Check-FileHead $jobId3 "source_manifest.json"

Write-Section "TEST 4: photo upload should create image_approximated or fallback with image reports"
$photoPath = "C:\Users\31175\Desktop\tuzhifenjie\backend\test_assets\sample_connector_photo.png"

if (Test-Path $photoPath) {
  $form = @{
    input_type = "photo"
    file = Get-Item $photoPath
  }

  $job4 = Invoke-RestMethod "$Base/api/connector-cad/jobs" -Method Post -Form $form
  $job4 | ConvertTo-Json -Depth 10

  $jobId4 = $job4.job_id
  $params4 = Get-JobParams $jobId4
  $params4 | ConvertTo-Json -Depth 20

  Write-Host "ASSERT model_origin should be image_approximated or generic_mvp:" $params4.model_origin
  Write-Host "Appearance pipeline:" ($params4.appearance_pipeline | ConvertTo-Json -Depth 10)

  Check-FileHead $jobId4 "model.step"
  Check-FileHead $jobId4 "model.stl"
  Check-FileHead $jobId4 "drawing.dxf"
  Check-FileHead $jobId4 "params.json"
  Check-FileHead $jobId4 "source_manifest.json"
  Check-FileHead $jobId4 "image_features.json"
  Check-FileHead $jobId4 "vision_report.json"
} else {
  Write-Host "Photo test asset missing: $photoPath" -ForegroundColor Red
}

Write-Section "SUMMARY"
Write-Host "Test 1 job_id:" $jobId1
Write-Host "Test 2 job_id:" $jobId2
Write-Host "Test 3 job_id:" $jobId3
if ($jobId4) { Write-Host "Test 4 job_id:" $jobId4 }

Write-Host ""
Write-Host "Manual pass criteria:" -ForegroundColor Yellow
Write-Host "1. 1-968970-1 must be series_template + TE_BLUE_MULTI_CAVITY + blue."
Write-Host "2. LOCAL SAMPLE STEP must be official_cad."
Write-Host "3. Ordinary text must show AI success and not official_cad."
Write-Host "4. Photo upload must produce image feature files and not claim official CAD."
