```ts
export type PaperNote = {
  citationKey: string;
  question: string;
  followUp?: string;
};

export function openQuestions(notes: PaperNote[]): string[] {
  return notes
    .filter((note) => note.followUp !== undefined)
    .map((note) => note.question);
}
```
