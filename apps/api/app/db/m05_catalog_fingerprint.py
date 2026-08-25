"""0100 기준선 이후 catalog drift를 검증하기 위한 공통 fingerprint."""

from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.engine import Connection

_FINGERPRINT_SESSION_STATEMENTS = (
    "SET LOCAL TIME ZONE 'UTC'",
    "SET LOCAL DateStyle TO 'ISO, YMD'",
    "SET LOCAL IntervalStyle TO 'iso_8601'",
    "SET LOCAL bytea_output TO 'hex'",
    "SET LOCAL extra_float_digits TO 3",
    "SET LOCAL search_path TO pg_catalog, app, public",
)

_CATALOG_FINGERPRINT_SQL = """
WITH object_lines(line) AS (
  SELECT jsonb_build_array(
      'schema', namespace.nspname, pg_get_userbyid(namespace.nspowner),
      COALESCE(namespace.nspacl::text, acldefault('n', namespace.nspowner)::text)
    )::text
  FROM pg_namespace AS namespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'relation', relation.relname, relation.relkind, relation.relpersistence,
      relation.relreplident, pg_get_userbyid(relation.relowner),
      COALESCE(relation.reloptions::text, ''), COALESCE(relation.relacl::text, ''),
      relation.relrowsecurity, relation.relforcerowsecurity, relation.relispartition,
      COALESCE(pg_get_expr(relation.relpartbound, relation.oid, true), ''),
      COALESCE(pg_get_partkeydef(relation.oid), ''),
      COALESCE(sequence_row.seqstart::text, ''), COALESCE(sequence_row.seqmin::text, ''),
      COALESCE(sequence_row.seqmax::text, ''), COALESCE(sequence_row.seqincrement::text, ''),
      COALESCE(sequence_row.seqcache::text, ''), COALESCE(sequence_row.seqcycle::text, ''),
      CASE WHEN sequence_row.seqtypid IS NULL THEN ''
           ELSE sequence_row.seqtypid::regtype::text END,
      CASE WHEN relation.relkind IN ('v', 'm')
           THEN pg_get_viewdef(relation.oid, true) ELSE '' END,
      COALESCE((
        SELECT jsonb_agg(
          jsonb_build_array(
            dependency.deptype, referenced_namespace.nspname,
            referenced_relation.relname,
            CASE WHEN dependency.refobjsubid = 0 THEN ''
                 ELSE referenced_attribute.attname END
          )
          ORDER BY dependency.deptype, referenced_namespace.nspname,
                   referenced_relation.relname, dependency.refobjsubid
        )::text
        FROM pg_depend AS dependency
        JOIN pg_class AS referenced_relation
          ON dependency.refclassid = 'pg_class'::regclass
         AND dependency.refobjid = referenced_relation.oid
        JOIN pg_namespace AS referenced_namespace
          ON referenced_namespace.oid = referenced_relation.relnamespace
        LEFT JOIN pg_attribute AS referenced_attribute
          ON referenced_attribute.attrelid = dependency.refobjid
         AND referenced_attribute.attnum = dependency.refobjsubid
         AND NOT referenced_attribute.attisdropped
        WHERE dependency.classid = 'pg_class'::regclass
          AND dependency.objid = relation.oid
          AND dependency.deptype = 'a'
      ), '')
    )::text
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  LEFT JOIN pg_sequence AS sequence_row ON sequence_row.seqrelid = relation.oid
  WHERE namespace.nspname IN ('app', 'x_extension')
    AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'c')
  UNION ALL
  SELECT jsonb_build_array(
      'column', relation.relname, attribute.attname, attribute.attnum,
      pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
      attribute.attnotnull, attribute.attidentity, attribute.attgenerated,
      COALESCE(pg_get_expr(default_value.adbin, default_value.adrelid), ''),
      COALESCE(attribute.attcollation::regcollation::text, ''),
      COALESCE(attribute.attacl::text, '')
    )::text
  FROM pg_attribute AS attribute
  JOIN pg_class AS relation ON relation.oid = attribute.attrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  LEFT JOIN pg_attrdef AS default_value
    ON default_value.adrelid = attribute.attrelid
   AND default_value.adnum = attribute.attnum
  WHERE namespace.nspname IN ('app', 'x_extension')
    AND relation.relkind IN ('r', 'p', 'v', 'm', 'f', 'c')
    AND attribute.attnum > 0 AND NOT attribute.attisdropped
  UNION ALL
  SELECT jsonb_build_array(
      'type', type_row.typname, type_row.typtype,
      pg_get_userbyid(type_row.typowner), COALESCE(type_row.typacl::text, ''),
      CASE WHEN type_row.typbasetype = 0 THEN ''
           ELSE pg_catalog.format_type(type_row.typbasetype, type_row.typtypmod) END,
      type_row.typnotnull, COALESCE(type_row.typdefault, ''),
      CASE WHEN type_row.typcollation = 0 THEN ''
           ELSE type_row.typcollation::regcollation::text END
    )::text
  FROM pg_type AS type_row
  JOIN pg_namespace AS namespace ON namespace.oid = type_row.typnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
    AND type_row.typrelid = 0 AND type_row.typelem = 0 AND type_row.typtype <> 'p'
  UNION ALL
  SELECT jsonb_build_array(
      'enum', type_row.typname, enum_row.enumsortorder, enum_row.enumlabel
    )::text
  FROM pg_enum AS enum_row
  JOIN pg_type AS type_row ON type_row.oid = enum_row.enumtypid
  JOIN pg_namespace AS namespace ON namespace.oid = type_row.typnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'constraint', relation.relname, constraint_row.conname, constraint_row.contype,
      constraint_row.condeferrable, constraint_row.condeferred,
      constraint_row.convalidated, constraint_row.conkey::text,
      CASE WHEN constraint_row.confrelid = 0 THEN ''
           ELSE constraint_row.confrelid::regclass::text END,
      constraint_row.confkey::text, constraint_row.confupdtype,
      constraint_row.confdeltype, constraint_row.confmatchtype,
      pg_get_constraintdef(constraint_row.oid, true)
    )::text
  FROM pg_constraint AS constraint_row
  JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'domain_constraint', type_row.typname, constraint_row.conname,
      constraint_row.condeferrable, constraint_row.condeferred,
      constraint_row.convalidated, pg_get_constraintdef(constraint_row.oid, true)
    )::text
  FROM pg_constraint AS constraint_row
  JOIN pg_type AS type_row ON type_row.oid = constraint_row.contypid
  JOIN pg_namespace AS namespace ON namespace.oid = type_row.typnamespace
  WHERE namespace.nspname IN ('app', 'x_extension') AND constraint_row.contypid <> 0
  UNION ALL
  SELECT jsonb_build_array(
      'index', table_rel.relname, index_rel.relname, index_row.indisunique,
      index_row.indisprimary, index_row.indisvalid, index_row.indisready,
      index_row.indkey::text, index_row.indclass::text, index_row.indcollation::text,
      index_row.indoption::text, pg_get_indexdef(index_row.indexrelid),
      COALESCE(pg_get_expr(index_row.indexprs, index_row.indrelid, true), ''),
      COALESCE(pg_get_expr(index_row.indpred, index_row.indrelid, true), '')
    )::text
  FROM pg_index AS index_row
  JOIN pg_class AS table_rel ON table_rel.oid = index_row.indrelid
  JOIN pg_class AS index_rel ON index_rel.oid = index_row.indexrelid
  JOIN pg_namespace AS namespace ON namespace.oid = table_rel.relnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'function', procedure.oid::regprocedure::text, language.lanname,
      procedure.prosecdef, procedure.proleakproof, procedure.proisstrict,
      procedure.provolatile, procedure.proparallel, COALESCE(procedure.proconfig::text, ''),
      COALESCE(procedure.prosrc, ''), COALESCE(procedure.proacl::text, '')
    )::text
  FROM pg_proc AS procedure
  JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
  JOIN pg_language AS language ON language.oid = procedure.prolang
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'trigger', relation.relname, trigger_row.tgname, trigger_row.tgenabled,
      trigger_row.tgtype, trigger_row.tgdeferrable, trigger_row.tginitdeferred,
      trigger_row.tgparentid, trigger_row.tgfoid::regprocedure::text,
      encode(trigger_row.tgargs, 'hex'), trigger_row.tgattr::text,
      COALESCE(pg_get_expr(trigger_row.tgqual, trigger_row.tgrelid, true), '')
    )::text
  FROM pg_trigger AS trigger_row
  JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname IN ('app', 'x_extension') AND NOT trigger_row.tgisinternal
  UNION ALL
  SELECT jsonb_build_array(
      'policy', relation.relname, policy.polname, policy.polpermissive, policy.polcmd,
      COALESCE(array_to_string(ARRAY(
        SELECT pg_get_userbyid(role_oid)
        FROM unnest(policy.polroles) AS role_oid
        ORDER BY pg_get_userbyid(role_oid)
      ), ','), ''), COALESCE(pg_get_expr(policy.polqual, policy.polrelid, true), ''),
      COALESCE(pg_get_expr(policy.polwithcheck, policy.polrelid, true), '')
    )::text
  FROM pg_policy AS policy
  JOIN pg_class AS relation ON relation.oid = policy.polrelid
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'rule', relation.relname, rewrite.rulename, rewrite.ev_type,
      rewrite.ev_enabled, rewrite.is_instead, pg_get_ruledef(rewrite.oid, true)
    )::text
  FROM pg_rewrite AS rewrite
  JOIN pg_class AS relation ON relation.oid = rewrite.ev_class
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'extension', extension_row.extname, extension_row.extversion,
      namespace.nspname, pg_get_userbyid(extension_row.extowner)
    )::text
  FROM pg_extension AS extension_row
  JOIN pg_namespace AS namespace ON namespace.oid = extension_row.extnamespace
  WHERE namespace.nspname IN ('app', 'x_extension')
  UNION ALL
  SELECT jsonb_build_array(
      'collation', collation_row.collname, collation_row.collprovider,
      collation_row.collisdeterministic, collation_row.collencoding,
      COALESCE(collation_row.collcollate, ''), COALESCE(collation_row.collctype, ''),
      COALESCE(collation_row.colliculocale, ''), COALESCE(collation_row.collicurules, ''),
      COALESCE(collation_row.collversion, ''), pg_get_userbyid(collation_row.collowner)
    )::text
  FROM pg_collation AS collation_row
  JOIN pg_namespace AS namespace ON namespace.oid = collation_row.collnamespace
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'conversion', conversion_row.conname, conversion_row.conforencoding,
      conversion_row.contoencoding, conversion_row.conproc::regproc::text,
      conversion_row.condefault, pg_get_userbyid(conversion_row.conowner)
    )::text
  FROM pg_conversion AS conversion_row
  JOIN pg_namespace AS namespace ON namespace.oid = conversion_row.connamespace
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'opclass', opclass_row.opcname, access_method.amname, family_row.opfname,
      opclass_row.opcdefault, opclass_row.opcintype::regtype::text,
      opclass_row.opckeytype::regtype::text, pg_get_userbyid(opclass_row.opcowner)
    )::text
  FROM pg_opclass AS opclass_row
  JOIN pg_namespace AS namespace ON namespace.oid = opclass_row.opcnamespace
  JOIN pg_am AS access_method ON access_method.oid = opclass_row.opcmethod
  JOIN pg_opfamily AS family_row ON family_row.oid = opclass_row.opcfamily
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'opfamily', opfamily_row.opfname, access_method.amname,
      pg_get_userbyid(opfamily_row.opfowner)
    )::text
  FROM pg_opfamily AS opfamily_row
  JOIN pg_namespace AS namespace ON namespace.oid = opfamily_row.opfnamespace
  JOIN pg_am AS access_method ON access_method.oid = opfamily_row.opfmethod
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'ts_config', config_row.cfgname, config_row.cfgparser::regproc::text,
      pg_get_userbyid(config_row.cfgowner)
    )::text
  FROM pg_ts_config AS config_row
  JOIN pg_namespace AS namespace ON namespace.oid = config_row.cfgnamespace
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'ts_dict', dictionary_row.dictname, dictionary_row.dicttemplate::regproc::text,
      COALESCE(dictionary_row.dictinitoption, ''), pg_get_userbyid(dictionary_row.dictowner)
    )::text
  FROM pg_ts_dict AS dictionary_row
  JOIN pg_namespace AS namespace ON namespace.oid = dictionary_row.dictnamespace
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'statistic_ext', statistic_row.stxname, statistic_row.stxstattarget,
      statistic_row.stxkeys::text, statistic_row.stxkind::text,
      COALESCE(statistic_row.stxexprs::text, ''),
      pg_get_statisticsobjdef(statistic_row.oid), pg_get_userbyid(statistic_row.stxowner)
    )::text
  FROM pg_statistic_ext AS statistic_row
  JOIN pg_namespace AS namespace ON namespace.oid = statistic_row.stxnamespace
  WHERE namespace.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'default_acl', COALESCE(namespace.nspname, ''),
      default_acl.defaclrole::regrole::text, default_acl.defaclobjtype,
      COALESCE(default_acl.defaclacl::text, '')
    )::text
  FROM pg_default_acl AS default_acl
  LEFT JOIN pg_namespace AS namespace ON namespace.oid = default_acl.defaclnamespace
  WHERE namespace.nspname IN ('app', 'x_extension') OR namespace.nspname IS NULL
)
SELECT line FROM object_lines ORDER BY line COLLATE "C"
"""


def catalog_fingerprint(bind: Connection) -> tuple[int, str]:
    """Return the ordered fresh-baseline catalog row count and digest."""

    for statement in _FINGERPRINT_SESSION_STATEMENTS:
        bind.execute(text(statement))
    rows = tuple(str(line) for line in bind.execute(text(_CATALOG_FINGERPRINT_SQL)).scalars())
    payload = ("\n".join(rows) + "\n").encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()
