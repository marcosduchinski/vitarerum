import { TestBed } from '@angular/core/testing';

import { providePublicI18nTesting } from '../../i18n/public-i18n.testing';
import { TurnstileComponent } from './turnstile.component';

describe('TurnstileComponent', () => {
  const render = vi.fn(() => 'widget-1');
  const reset = vi.fn();
  const remove = vi.fn();

  beforeEach(async () => {
    render.mockClear();
    reset.mockClear();
    remove.mockClear();
    window.turnstile = { render, reset, remove };

    await TestBed.configureTestingModule({
      imports: [TurnstileComponent],
      providers: [providePublicI18nTesting()],
    }).compileComponents();
  });

  afterEach(() => {
    delete window.turnstile;
  });

  it('removes the explicitly rendered widget when Angular destroys the component', async () => {
    const fixture = TestBed.createComponent(TurnstileComponent);
    fixture.componentRef.setInput('siteKey', 'site-key');
    fixture.detectChanges();
    await fixture.whenStable();

    expect(render).toHaveBeenCalledOnce();
    expect(remove).not.toHaveBeenCalled();

    fixture.destroy();

    expect(remove).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith('widget-1');
  });

  it('does not reset a widget after it has been destroyed', async () => {
    const fixture = TestBed.createComponent(TurnstileComponent);
    fixture.componentRef.setInput('siteKey', 'site-key');
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;

    fixture.destroy();
    component.reset();

    expect(reset).not.toHaveBeenCalled();
  });
});
