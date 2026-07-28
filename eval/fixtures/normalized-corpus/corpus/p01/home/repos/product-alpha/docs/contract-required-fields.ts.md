```ts
/** API 契約の変更で必須項目が欠けていないかを確認する。 */
export type ContractField = {
  name: string;
  required: boolean;
  description?: string;
};

export function undocumentedRequiredFields(fields: ContractField[]): string[] {
  return fields
    .filter((field) => field.required && !field.description?.trim())
    .map((field) => field.name)
    .sort();
}

export function changedRequiredFields(before: ContractField[], after: ContractField[]): string[] {
  const previous = new Map(before.map((field) => [field.name, field.required]));
  return after
    .filter((field) => previous.has(field.name) && previous.get(field.name) !== field.required)
    .map((field) => field.name)
    .sort();
}
```
