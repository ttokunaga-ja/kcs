```ts
export type SharedArtifact = {
  title: string;
  ownerTeam: "Applied Foundations";
  visibility: "team";
  collectionRevision: string;
};

export function makeManifest(title: string, collectionRevision: string): SharedArtifact {
  return {
    title,
    ownerTeam: "Applied Foundations",
    visibility: "team",
    collectionRevision,
  };
}
```
