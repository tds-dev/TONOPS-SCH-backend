"""Order系の作成SQL・挿入SQLがモデルと同じ構造・参照関係を持つことを確認するテスト。"""
from datetime import datetime
import re
import unittest
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import Base, make_engine
from app.models.transactions import Order, Task
from scripts.export_ddl import render_database_sql, render_schema_sql
from scripts.export_seed_sql import demo_rows, render_seed_sql, sql_value


class ExportSqlTest(unittest.TestCase):
    """SQL生成だけを検証し、実DBへの接続・実行を行わない。"""

    def test_schema_uses_order_names_and_includes_deferred_foreign_key(self):
        # 通常の外部キーに加え、後から追加する相互参照も含まれることを確認する。
        sql = render_schema_sql()
        self.assertEqual(sql.count('CREATE TABLE '), len(Base.metadata.tables))
        self.assertIn('CREATE TABLE [T_Orders]', sql)
        self.assertIn('[OrderID]', sql)
        self.assertIn('[OrderType]', sql)
        self.assertIn('[ResourceType]', sql)
        self.assertNotIn('OrderKind', sql)
        self.assertNotIn('ResourceKind', sql)
        self.assertNotIn('T_Jobs', sql)
        self.assertNotIn('JobID', sql)
        self.assertIn('ALTER TABLE [M_Sites] ADD CONSTRAINT', sql)
        self.assertIn('FOREIGN KEY([DefaultCalendarID]) REFERENCES [M_Calendars]', sql)
        self.assertEqual(sql, render_schema_sql())
        self.assertIn('CREATE DATABASE [TONOPS-SCH]', render_database_sql())

    def test_seed_sql_recreates_same_order_and_task_relationships(self):
        # 出力したINSERTと後続UPDATEを別のメモリDBへ読み込み、参照関係を確認する。
        rows = demo_rows(datetime(2026, 10, 30, 10, tzinfo=ZoneInfo('Asia/Tokyo')))
        sql = render_seed_sql(rows)
        self.assertEqual(len(rows['T_Orders']), 7)
        self.assertEqual(len(rows['T_Tasks']), 21)
        self.assertNotIn('T_Jobs', sql)
        self.assertNotIn('JobID', sql)
        self.assertIn('UPDATE [M_Sites] SET [DefaultCalendarID]', sql)
        engine = make_engine('sqlite://')
        try:
            Base.metadata.create_all(engine)
            with engine.begin() as connection:
                for line in sql.splitlines():
                    if line.startswith(('INSERT INTO ', 'UPDATE ')):
                        # SQLiteではSQL Server専用のUnicode接頭辞だけを外す。
                        sqlite_line = re.sub(r"N?'(?:[^']|'')*'", lambda match: match[0][1:] if match[0].startswith("N'") else match[0], line)
                        connection.exec_driver_sql(sqlite_line)
                inserted_orders = connection.execute(select(Order.__table__)).mappings().all()
                inserted_tasks = connection.execute(select(Task.__table__)).mappings().all()
                self.assertEqual(len(inserted_orders), 7)
                self.assertEqual(len(inserted_tasks), 21)
                self.assertEqual({row['OrderID'] for row in inserted_tasks}, {row['OrderID'] for row in inserted_orders})
                self.assertEqual(inserted_orders[0]['OrderNo'], rows['T_Orders'][0]['OrderNo'])
        finally:
            engine.dispose()

    def test_sql_values_preserve_japanese_and_escape_quotes(self):
        # 日本語、引用符、JSON、NULL、真偽値が壊れないことを確認する。
        self.assertEqual(sql_value("日本語'O"), "N'日本語''O'")
        self.assertEqual(sql_value({'名称': "A'B"}), 'N\'{"名称": "A\'\'B"}\'')
        self.assertEqual(sql_value(None), 'NULL')
        self.assertEqual(sql_value(True), '1')
