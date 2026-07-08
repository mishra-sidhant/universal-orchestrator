import unittest

from universal_orchestrator.models import TaskDAG, TaskNode, TaskType


class TaskDAGTests(unittest.TestCase):
    def test_topological_order_sorts_dependencies_first(self) -> None:
        dag = TaskDAG(
            run_id="run_test",
            nodes=[
                TaskNode(id="B", run_id="run_test", title="B", task_type=TaskType.PLANNING, dependencies=["A"]),
                TaskNode(id="A", run_id="run_test", title="A", task_type=TaskType.PLANNING),
            ],
        )

        self.assertEqual([node.id for node in dag.topological_order()], ["A", "B"])

    def test_cycle_is_rejected(self) -> None:
        dag = TaskDAG(
            run_id="run_test",
            nodes=[
                TaskNode(id="A", run_id="run_test", title="A", task_type=TaskType.PLANNING, dependencies=["B"]),
                TaskNode(id="B", run_id="run_test", title="B", task_type=TaskType.PLANNING, dependencies=["A"]),
            ],
        )

        with self.assertRaises(ValueError):
            dag.validate_graph()


if __name__ == "__main__":
    unittest.main()

