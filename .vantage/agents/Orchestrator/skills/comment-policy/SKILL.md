---
name: comment-policy
description: "Enforces C# commenting and #region conventions for the workspace."
---

This skill encodes the workspace commenting and #region conventions for C# files.

# Comment Policy

This file defines the mandatory commenting and `#region` conventions for all C# code produced or
reviewed in this workspace. Apply these rules whenever the Senior Developer writes code or the Code
Reviewer audits it.

## Scope

- Language: C# (applies to all `.cs` files)
- Enforced by: Senior Developer (during implementation) and Code Reviewer (during review)
- Orchestrator enforcement: include a "Commenting and Region compliance" line in the Code Reviewer
  contract findings and in the Senior Developer implementation summary

---

## 1. Commenting Rules

### 1.1 Classes

| Visibility | Required comment style |
|---|---|
| `public` | Full XML `<summary>` doc comment |
| `internal` | XML `<summary>` doc comment |
| `private` (nested) | XML `<summary>` doc comment or a meaningful `//` block above the declaration |
| `abstract` / `sealed` | XML `<summary>` plus `<remarks>` describing design intent or extension contract |

Example — public class:

```csharp
/// <summary>
/// Manages ID allocation sequences for Oracle and SQL Server databases.
/// </summary>
public class IdAllocationService
{
}
```

Example — private nested class:

```csharp
// Compares (Schema, Table) tuples using OrdinalIgnoreCase for both components.
private sealed class TableNameComparer : IEqualityComparer<(string Schema, string Table)>
{
}
```

### 1.2 Methods

| Visibility | Required comment style |
|---|---|
| `public` | Full XML doc: `<summary>`, `<param>` per parameter, `<returns>` (if non-void), `<exception>` for documented throws |
| `protected` | Same as `public` |
| `internal` | XML `<summary>` and `<param>` at minimum |
| `private` | XML `<summary>` OR a clear `//` comment explaining intent; skip only when the name is entirely self-documenting and the body fits in ≤ 5 lines |
| Override | `/// <inheritdoc/>` when behavior is unchanged; add `<remarks>` if behavior differs |
| Async methods | Note async nature and cancellation behavior in `<remarks>` when non-obvious |

Example — public method:

```csharp
/// <summary>
/// Retrieves all active sequences registered in the Oracle database.
/// </summary>
/// <param name="schemaFilter">Optional schema name to restrict results.</param>
/// <returns>A read-only list of sequence names.</returns>
/// <exception cref="OracleException">Thrown when the database connection fails.</exception>
public IReadOnlyList<string> GetSequencesInOracle(string? schemaFilter = null)
{
}
```

Example — private method (self-documenting name, short body — inline comment acceptable):

```csharp
// Maps a raw sequence name to its normalized (schema, table) tuple.
private (string Schema, string Table) ParseSequenceName(string rawName)
{
}
```

Example — override:

```csharp
/// <inheritdoc/>
/// <remarks>Skips the database Load() call for Oracle because the in-memory cache is already populated.</remarks>
public override async Task SaveChangesAsync(CancellationToken cancellationToken = default)
{
}
```

### 1.3 Fields

| Visibility | Required comment style |
|---|---|
| `public` | XML `<summary>` doc comment |
| `internal` | XML `<summary>` doc comment |
| `private` / `private readonly` | Inline `//` comment when the name alone does not convey purpose; omit only for trivially obvious fields (e.g., `_cancellationToken`) |
| Constants (`const` / `static readonly`) | Inline `//` comment or XML `<summary>` explaining the value's semantic meaning |

Example — private field:

```csharp
// Cached OrdinalIgnoreCase comparer reused across all lookups.
private readonly StringComparer _stringComparer = StringComparer.OrdinalIgnoreCase;

// Number of prefix characters stripped from raw Oracle sequence names.
private const int SequencePrefixLength = 2;
```

### 1.4 Properties

| Visibility | Required comment style |
|---|---|
| `public` | XML `<summary>`; add `<value>` tag when the returned value is non-obvious |
| `protected` | XML `<summary>` |
| `internal` | XML `<summary>` |
| `private` | Inline `//` comment when name is not self-documenting; omit for obvious auto-properties |

Example — public property:

```csharp
/// <summary>
/// Gets the default schema name used when no schema is explicitly specified.
/// </summary>
/// <value>Always <c>"dbo"</c> for SQL Server targets.</value>
public string DefaultSchema { get; } = "dbo";
```

---

## 2. Region Management Rules

### 2.1 Canonical Region Order

Every class body must organize members into regions in this fixed order.
Omit a region entirely when no members of that category exist.

```
#region Constants
#region Fields
#region Properties
#region Constructors
#region Public Methods
#region Protected Methods
#region Private Methods
#region Event Handlers
#region Nested Types
```

### 2.2 Region Label Convention

- Region open label and the matching `#endregion` label must be identical.
- Use Title Case with spaces (e.g., `Public Methods`, not `publicMethods` or `PUBLIC_METHODS`).
- Always include the label on `#endregion` for readability.

```csharp
#region Public Methods

// ... members ...

#endregion Public Methods
```

### 2.3 Region Size Rules

- Minimum 2 members required to justify a region; a single-member region is not permitted.
- Maximum nesting depth: 1 sub-region inside a parent region (e.g., `Async Overloads` inside
  `Public Methods`). Deeper nesting is not permitted.
- Sub-region label must clearly qualify the parent context:

```csharp
#region Public Methods

    #region Async Overloads

    // ...

    #endregion Async Overloads

#endregion Public Methods
```

### 2.4 Region Ordering Rules

- Do not reorder regions arbitrarily within an existing file; follow the canonical order.
- When adding members to an existing file that does not yet use regions, add regions as part of
  the same change rather than mixing region and non-region styles within one class.
- Interface-implementing members go in the region matching their visibility (usually `Public Methods`).
  Add an inline `// --- IInterfaceName ---` separator comment when grouping implementations aids clarity.

### 2.5 Prohibited Region Uses

- Do not create regions spanning multiple classes or structs.
- Do not use regions to hide large blocks of commented-out code; delete unused code instead.
- Do not use regions inside method bodies.

---

## 3. Quick Compliance Checklist

Use this checklist during Code Reviewer evaluation and Senior Developer self-review.

### Commenting

- [ ] Every public/internal class has an XML `<summary>`
- [ ] Every public/protected method has `<summary>`, `<param>`, and `<returns>`
- [ ] Private methods have at least a `<summary>` or a meaningful `//` comment
- [ ] Override methods use `<inheritdoc/>` (with `<remarks>` if behavior differs)
- [ ] Async methods document cancellation behavior when non-trivial
- [ ] Public/internal fields and properties have XML `<summary>`
- [ ] Private fields have `//` comment unless trivially obvious
- [ ] Constants have `//` comment or XML `<summary>` explaining semantic meaning

### Regions

- [ ] Regions follow the canonical order (Constants → Fields → Properties → Constructors →
  Public Methods → Protected Methods → Private Methods → Event Handlers → Nested Types)
- [ ] Every `#region` has a matching `#endregion` with an identical label
- [ ] No region contains fewer than 2 members
- [ ] Region nesting depth does not exceed 1 level
- [ ] No regions exist inside method bodies
- [ ] No regions used to hide commented-out code

```yaml
pseudocode_comment_and_region_check: |
  # Pseudocode: Validate commenting and region rules for a .cs file

  function check_file_compliance(file_path):
    parse_ast = parse_csharp_file(file_path)
    findings = []

    for each type_decl in parse_ast.type_declarations:
      # Check class/struct comments
      if type_decl.visibility in [public, internal] and not has_xml_summary(type_decl):
        findings.append({level: 'High', issue: 'Missing XML <summary> on type', location: type_decl.location})

      # Verify regions order and presence
      regions = extract_regions(type_decl)
      canonical = ["Constants","Fields","Properties","Constructors","Public Methods","Protected Methods","Private Methods","Event Handlers","Nested Types"]
      if regions.count > 0:
        if not regions_in_canonical_order(regions, canonical):
          findings.append({level: 'Medium', issue: 'Regions out of canonical order', location: type_decl.location})
        for r in regions:
          if r.member_count < 2:
            findings.append({level: 'Medium', issue: 'Region has fewer than 2 members', region: r.label, location: r.location})

    # Methods/fields/properties checks
    for member in parse_ast.members:
      if member.is_public_or_protected and not has_xml_summary(member):
        findings.append({level: 'High', issue: 'Missing XML <summary> on public/protected member', location: member.location})
      if member.is_private and not has_comment(member) and not is_trivial(member):
        findings.append({level: 'Low', issue: 'Private member lacking explanatory comment', location: member.location})

    # Return findings list
    return findings

  # Usage: call check_file_compliance for changed .cs files during review or CI.
```

| Visibility | Required comment style |
|---|---|
| `public` | Full XML doc: `<summary>`, `<param>` per parameter, `<returns>` (if non-void), `<exception>` for documented throws |
| `protected` | Same as `public` |
| `internal` | XML `<summary>` and `<param>` at minimum |
| `private` | XML `<summary>` OR a clear `//` comment explaining intent; skip only when the name is entirely self-documenting and the body fits in ≤ 5 lines |
| Override | `/// <inheritdoc/>` when behavior is unchanged; add `<remarks>` if behavior differs |
| Async methods | Note async nature and cancellation behavior in `<remarks>` when non-obvious |

Example — public method:

```csharp
/// <summary>
/// Retrieves all active sequences registered in the Oracle database.
/// </summary>
/// <param name="schemaFilter">Optional schema name to restrict results.</param>
/// <returns>A read-only list of sequence names.</returns>
/// <exception cref="OracleException">Thrown when the database connection fails.</exception>
public IReadOnlyList<string> GetSequencesInOracle(string? schemaFilter = null)
{
}
```

Example — private method (self-documenting name, short body — inline comment acceptable):

```csharp
// Maps a raw sequence name to its normalized (schema, table) tuple.
private (string Schema, string Table) ParseSequenceName(string rawName)
{
}
```

Example — override:

```csharp
/// <inheritdoc/>
/// <remarks>Skips the database Load() call for Oracle because the in-memory cache is already populated.</remarks>
public override async Task SaveChangesAsync(CancellationToken cancellationToken = default)
{
}
```

### 1.3 Fields

| Visibility | Required comment style |
|---|---|
| `public` | XML `<summary>` doc comment |
| `internal` | XML `<summary>` doc comment |
| `private` / `private readonly` | Inline `//` comment when the name alone does not convey purpose; omit only for trivially obvious fields (e.g., `_cancellationToken`) |
| Constants (`const` / `static readonly`) | Inline `//` comment or XML `<summary>` explaining the value's semantic meaning |

Example — private field:

```csharp
// Cached OrdinalIgnoreCase comparer reused across all lookups.
private readonly StringComparer _stringComparer = StringComparer.OrdinalIgnoreCase;

// Number of prefix characters stripped from raw Oracle sequence names.
private const int SequencePrefixLength = 2;
```

### 1.4 Properties

| Visibility | Required comment style |
|---|---|
| `public` | XML `<summary>`; add `<value>` tag when the returned value is non-obvious |
| `protected` | XML `<summary>` |
| `internal` | XML `<summary>` |
| `private` | Inline `//` comment when name is not self-documenting; omit for obvious auto-properties |

Example — public property:

```csharp
/// <summary>
/// Gets the default schema name used when no schema is explicitly specified.
/// </summary>
/// <value>Always <c>"dbo"</c> for SQL Server targets.</value>
public string DefaultSchema { get; } = "dbo";
```

---

## 2. Region Management Rules

### 2.1 Canonical Region Order

Every class body must organize members into regions in this fixed order.
Omit a region entirely when no members of that category exist.

```
#region Constants
#region Fields
#region Properties
#region Constructors
#region Public Methods
#region Protected Methods
#region Private Methods
#region Event Handlers
#region Nested Types
```

### 2.2 Region Label Convention

- Region open label and the matching `#endregion` label must be identical.
- Use Title Case with spaces (e.g., `Public Methods`, not `publicMethods` or `PUBLIC_METHODS`).
- Always include the label on `#endregion` for readability.

```csharp
#region Public Methods

// ... members ...

#endregion Public Methods
```

### 2.3 Region Size Rules

- Minimum 2 members required to justify a region; a single-member region is not permitted.
- Maximum nesting depth: 1 sub-region inside a parent region (e.g., `Async Overloads` inside
  `Public Methods`). Deeper nesting is not permitted.
- Sub-region label must clearly qualify the parent context:

```csharp
#region Public Methods

    #region Async Overloads

    // ...

    #endregion Async Overloads

#endregion Public Methods
```

### 2.4 Region Ordering Rules

- Do not reorder regions arbitrarily within an existing file; follow the canonical order.
- When adding members to an existing file that does not yet use regions, add regions as part of
  the same change rather than mixing region and non-region styles within one class.
- Interface-implementing members go in the region matching their visibility (usually `Public Methods`).
  Add an inline `// --- IInterfaceName ---` separator comment when grouping implementations aids clarity.

### 2.5 Prohibited Region Uses

- Do not create regions spanning multiple classes or structs.
- Do not use regions to hide large blocks of commented-out code; delete unused code instead.
- Do not use regions inside method bodies.

---

## 3. Quick Compliance Checklist

Use this checklist during Code Reviewer evaluation and Senior Developer self-review.

### Commenting

- [ ] Every public/internal class has an XML `<summary>`
- [ ] Every public/protected method has `<summary>`, `<param>`, and `<returns>`
- [ ] Private methods have at least a `<summary>` or a meaningful `//` comment
- [ ] Override methods use `<inheritdoc/>` (with `<remarks>` if behavior differs)
- [ ] Async methods document cancellation behavior when non-trivial
- [ ] Public/internal fields and properties have XML `<summary>`
- [ ] Private fields have `//` comment unless trivially obvious
- [ ] Constants have `//` comment or XML `<summary>` explaining semantic meaning

### Regions

- [ ] Regions follow the canonical order (Constants → Fields → Properties → Constructors →
  Public Methods → Protected Methods → Private Methods → Event Handlers → Nested Types)
- [ ] Every `#region` has a matching `#endregion` with an identical label
- [ ] No region contains fewer than 2 members
- [ ] Region nesting depth does not exceed 1 level
- [ ] No regions exist inside method bodies
- [ ] No regions used to hide commented-out code

```yaml
pseudocode_comment_and_region_check: |
  # Pseudocode: Validate commenting and region rules for a .cs file

  function check_file_compliance(file_path):
    parse_ast = parse_csharp_file(file_path)
    findings = []

    for each type_decl in parse_ast.type_declarations:
      # Check class/struct comments
      if type_decl.visibility in [public, internal] and not has_xml_summary(type_decl):
        findings.append({level: 'High', issue: 'Missing XML <summary> on type', location: type_decl.location})

      # Verify regions order and presence
      regions = extract_regions(type_decl)
      canonical = ["Constants","Fields","Properties","Constructors","Public Methods","Protected Methods","Private Methods","Event Handlers","Nested Types"]
      if regions.count > 0:
        if not regions_in_canonical_order(regions, canonical):
          findings.append({level: 'Medium', issue: 'Regions out of canonical order', location: type_decl.location})
        for r in regions:
          if r.member_count < 2:
            findings.append({level: 'Medium', issue: 'Region has fewer than 2 members', region: r.label, location: r.location})

    # Methods/fields/properties checks
    for member in parse_ast.members:
      if member.is_public_or_protected and not has_xml_summary(member):
        findings.append({level: 'High', issue: 'Missing XML <summary> on public/protected member', location: member.location})
      if member.is_private and not has_comment(member) and not is_trivial(member):
        findings.append({level: 'Low', issue: 'Private member lacking explanatory comment', location: member.location})

    # Return findings list
    return findings

  # Usage: call check_file_compliance for changed .cs files during review or CI.
```
