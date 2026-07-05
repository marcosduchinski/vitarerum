import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AskMuseumReceivedPageComponent } from './ask-museum-received-page.component';

describe('AskMuseumReceivedPageComponent', () => {
  it('shows the confirmation message with the submitted e-mail', async () => {
    await TestBed.configureTestingModule({
      imports: [AskMuseumReceivedPageComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(AskMuseumReceivedPageComponent);
    fixture.componentRef.setInput('email', 'ana@example.test');
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('ana@example.test');
  });

  it('renders without an e-mail too', async () => {
    await TestBed.configureTestingModule({
      imports: [AskMuseumReceivedPageComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(AskMuseumReceivedPageComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Question received');
  });
});
