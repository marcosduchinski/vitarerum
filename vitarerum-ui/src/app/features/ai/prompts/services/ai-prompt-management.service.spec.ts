import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { AiPromptManagementService } from './ai-prompt-management.service';

describe('AiPromptManagementService', () => {
  let service: AiPromptManagementService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/' },
        AiPromptManagementService,
      ],
    });
    service = TestBed.inject(AiPromptManagementService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists prompt templates with filters', () => {
    service.listTemplates({ purpose: 'in_situ_narrative', status: 'published' }).subscribe();

    const request = http.expectOne(
      'https://api.example.test/ai/prompts?purpose=in_situ_narrative&status=published',
    );
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('lists versions for a template', () => {
    service.listVersions('tpl-1').subscribe();
    const request = http.expectOne('https://api.example.test/ai/prompts/tpl-1/versions');
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('gets an immutable version by id', () => {
    service.getVersion('ver-1').subscribe();
    const request = http.expectOne('https://api.example.test/ai/prompts/versions/ver-1');
    expect(request.request.method).toBe('GET');
    request.flush({});
  });

  it('creates a draft with the API request shape', () => {
    service
      .createDraft('tpl-1', {
        versionLabel: 'museum-narrative-institutional-v2',
        content: 'Prompt',
        defaultTemperature: 0.3,
      })
      .subscribe();

    const request = http.expectOne('https://api.example.test/ai/prompts/tpl-1/versions');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      version_label: 'museum-narrative-institutional-v2',
      content: 'Prompt',
      default_temperature: 0.3,
      source_version_id: null,
    });
    request.flush({});
  });

  it('publishes and archives versions', () => {
    service.publishVersion('ver-1').subscribe();
    service.archiveVersion('ver-2').subscribe();

    const publish = http.expectOne('https://api.example.test/ai/prompts/versions/ver-1/publish');
    expect(publish.request.method).toBe('POST');
    publish.flush({});

    const archive = http.expectOne('https://api.example.test/ai/prompts/versions/ver-2/archive');
    expect(archive.request.method).toBe('POST');
    archive.flush({});
  });

  it('previews a narrative with the selected prompt version', () => {
    let result: unknown;
    service
      .previewNarrative({
        mode: 'version',
        recordId: 'record-1',
        promptVersionId: 'ver-draft',
        narrativeType: 'institutional',
        targetLanguage: 'pt',
        creativityTemperature: 0.4,
      })
      .subscribe((response) => {
        result = response;
      });

    const request = http.expectOne(
      'https://api.example.test/cidoc-mapping/in-situ-visit/record-1/narrative/preview',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      prompt_version_id: 'ver-draft',
      narrative_type: 'institutional',
      target_language: 'pt',
      creativity_temperature: 0.4,
    });
    request.flush({
      record_id: 'record-1',
      status: 'preview',
      generated_at: '2026-07-18T10:00:00Z',
      data: { narrative: 'Preview text.' },
      meta: {
        prompt_version_id: 'ver-draft',
        prompt_version: 'draft-v1',
        prompt_status: 'draft',
        prompt_source: 'version',
        llm_model: 'llama3.1:8b',
        creativity_temperature: 0.4,
        validation_conforms: true,
        model_response_hash: 'sha256:preview',
      },
    });

    expect(result).toEqual({
      recordId: 'record-1',
      status: 'preview',
      generatedAt: '2026-07-18T10:00:00Z',
      narrative: 'Preview text.',
      promptVersionId: 'ver-draft',
      promptVersion: 'draft-v1',
      promptStatus: 'draft',
      promptSource: 'version',
      llmModel: 'llama3.1:8b',
      creativityTemperature: 0.4,
      validationConforms: true,
      modelResponseHash: 'sha256:preview',
    });
  });

  it('previews a narrative with ad-hoc content', () => {
    let result: unknown;
    service
      .previewNarrative({
        mode: 'adhoc',
        recordId: 'record-1',
        content: 'Ad-hoc prompt',
        narrativeType: 'institutional',
        targetLanguage: 'pt',
        creativityTemperature: 0.5,
      })
      .subscribe((response) => {
        result = response;
      });

    const request = http.expectOne(
      'https://api.example.test/cidoc-mapping/in-situ-visit/record-1/narrative/preview',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      content: 'Ad-hoc prompt',
      narrative_type: 'institutional',
      target_language: 'pt',
      creativity_temperature: 0.5,
    });
    request.flush({
      record_id: 'record-1',
      status: 'preview',
      generated_at: '2026-07-18T10:00:00Z',
      data: { narrative: 'Preview text.' },
      meta: {
        prompt_version_id: null,
        prompt_version: null,
        prompt_status: null,
        prompt_source: 'adhoc',
        llm_model: 'llama3.1:8b',
        creativity_temperature: 0.5,
        validation_conforms: true,
        model_response_hash: 'sha256:preview',
      },
    });

    expect(result).toEqual({
      recordId: 'record-1',
      status: 'preview',
      generatedAt: '2026-07-18T10:00:00Z',
      narrative: 'Preview text.',
      promptVersionId: null,
      promptVersion: null,
      promptStatus: null,
      promptSource: 'adhoc',
      llmModel: 'llama3.1:8b',
      creativityTemperature: 0.5,
      validationConforms: true,
      modelResponseHash: 'sha256:preview',
    });
  });

  it('retries preview with the latest report record when a project id is provided', () => {
    let result: unknown;
    service
      .previewNarrative({
        mode: 'adhoc',
        recordId: 'project-1',
        content: 'Ad-hoc prompt',
        narrativeType: 'institutional',
        targetLanguage: 'pt',
        creativityTemperature: 0.5,
      })
      .subscribe((response) => {
        result = response;
      });

    const firstPreview = http.expectOne(
      'https://api.example.test/cidoc-mapping/in-situ-visit/project-1/narrative/preview',
    );
    expect(firstPreview.request.method).toBe('POST');
    firstPreview.flush(
      { message: 'No in-situ visit record found with id project-1' },
      { status: 404, statusText: 'Not Found' },
    );

    const reportLookup = http.expectOne(
      'https://api.example.test/reports/collection-use/project-1/in_situ_visit?page=0&size=1',
    );
    expect(reportLookup.request.method).toBe('GET');
    reportLookup.flush({
      content: [{ inSituVisitRecordId: 'record-from-project' }],
    });

    const retryPreview = http.expectOne(
      'https://api.example.test/cidoc-mapping/in-situ-visit/record-from-project/narrative/preview',
    );
    expect(retryPreview.request.method).toBe('POST');
    expect(retryPreview.request.body).toEqual({
      content: 'Ad-hoc prompt',
      narrative_type: 'institutional',
      target_language: 'pt',
      creativity_temperature: 0.5,
    });
    retryPreview.flush({
      record_id: 'record-from-project',
      status: 'preview',
      generated_at: '2026-07-18T10:00:00Z',
      data: { narrative: 'Preview text.' },
      meta: {
        prompt_version_id: null,
        prompt_version: null,
        prompt_status: null,
        prompt_source: 'adhoc',
        llm_model: 'llama3.1:8b',
        creativity_temperature: 0.5,
        validation_conforms: true,
        model_response_hash: 'sha256:preview',
      },
    });

    expect(result).toEqual(
      expect.objectContaining({
        recordId: 'record-from-project',
        narrative: 'Preview text.',
        promptSource: 'adhoc',
      }),
    );
  });
});
