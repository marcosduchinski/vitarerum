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
      llmModel: 'llama3.1:8b',
      creativityTemperature: 0.4,
      validationConforms: true,
      modelResponseHash: 'sha256:preview',
    });
  });
});
