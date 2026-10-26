/* Period links navigate; table sorting and search stay on the current page. */
(() => {
  const container = document.getElementById("performance-tables");
  if (!container || !window.DataTable) return;
  const tables = Array.from(container.querySelectorAll(".performance-table"));

  function updateHeadings(table) {
    table.querySelectorAll("button[data-sort]").forEach(heading => {
      const active = heading.dataset.sort === table.dataset.currentSort;
      const reversed = table.dataset.currentDirection === "asc" ? "desc" : "asc";
      heading.dataset.direction = active ? reversed : heading.dataset.defaultDirection;
      heading.querySelector(".sort-indicator").textContent = active
        ? (table.dataset.currentDirection === "asc" ? " ↑" : " ↓")
        : "";
    });
  }

  function enhanceTable(table) {
    const links = Array.from(table.querySelectorAll("button[data-sort]"));
    const initialColumn = links.findIndex(
      link => link.dataset.sort === table.dataset.currentSort
    );
    const dataTable = new window.DataTable(table, {
      paging: false,
      autoWidth: false,
      titleRow: 0,
      ordering: { handler: false, indicators: false },
      order: [[initialColumn, table.dataset.currentDirection]],
      // Department cells carry Python's alphabetical rank as their sort value.
      orderFixed: { post: [[0, "asc"]] },
      language: {
        search: "Find a department:",
        info: "Showing _TOTAL_ departments",
        infoEmpty: "No departments",
        infoFiltered: "(filtered from _MAX_ departments)"
      }
    });

    links.forEach(button => { button.disabled = false; });

    table.addEventListener("click", event => {
      const link = event.target.closest("button[data-sort]");
      if (
        !link || event.ctrlKey || event.metaKey || event.shiftKey ||
        event.altKey || event.button !== 0
      ) return;

      event.preventDefault();
      const direction = link.dataset.direction;
      const sort = link.dataset.sort;
      dataTable.order([[links.indexOf(link), direction]]).draw();
      table.dataset.currentSort = sort;
      table.dataset.currentDirection = direction;
      updateHeadings(table);
      // DataTables maintains aria-sort on the actual th elements during draw().
      const order = direction === "asc" ? "ascending" : "descending";
      document.getElementById(`${table.dataset.questionType}-sort-status`).textContent =
        `Sorted by ${link.dataset.label}, ${order}.`;
    });
  }

  tables.forEach(enhanceTable);
})();
