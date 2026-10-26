import {describe,expect,it} from 'vitest';
import {formatDate,formatDateTime,isOverdue} from './formatting';

describe('date formatting',()=>{
  it('formats date-only values as local calendar dates without UTC day shifts',()=>{
    const expected=new Date(2026,9,26).toLocaleDateString('ru-RU',{day:'2-digit',month:'short',year:'numeric'});
    expect(formatDate('2026-10-26')).toBe(expected);
  });
  it('uses explicit fallback labels for missing and invalid values',()=>{
    expect(formatDate(null)).toBe('Без срока');
    expect(formatDate('not-a-date')).toBe('Некорректная дата');
    expect(formatDateTime('not-a-date')).toBe('Некорректная дата');
    expect(formatDateTime(null)).toBe('—');
  });
  it('marks only unfinished tasks with a past due date as overdue',()=>{
    const now=new Date(2026,9,26,12,0,0);
    expect(isOverdue('2026-10-25','backlog',now)).toBe(true);
    expect(isOverdue('2026-10-26','in_progress',now)).toBe(false);
    expect(isOverdue('2026-10-25','done',now)).toBe(false);
    expect(isOverdue(null,'backlog',now)).toBe(false);
    expect(isOverdue('bad-date','backlog',now)).toBe(false);
  });
});
