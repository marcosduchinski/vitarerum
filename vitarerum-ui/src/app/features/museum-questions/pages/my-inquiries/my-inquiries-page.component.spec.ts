import { TestBed } from '@angular/core/testing';

import { MyInquiriesPageComponent } from './my-inquiries-page.component';

describe('MyInquiriesPageComponent', () => {
  it('renders the placeholder for future profile-based management', async () => {
    await TestBed.configureTestingModule({
      imports: [MyInquiriesPageComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(MyInquiriesPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('My inquiries');
    expect(compiled.textContent).toContain(
      'Profile-based inquiry management is not available yet.',
    );
  });
});
