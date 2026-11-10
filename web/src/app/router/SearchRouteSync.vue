<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useCoreClient } from '../../composables/useCoreClient'
import { routeSearchQuery } from './search-route'
const route = useRoute()
const { searchState } = useCoreClient()
let submitted = ''
// 根生命周期持有搜索状态，普通路由切换不会重建请求。
watch([() => route.path, () => route.query.q, searchState.sources], (_, previous) => {
  const q = routeSearchQuery(route.query.q)
  if (route.path !== '/search' || !q || !searchState.sources.value.length) return
  // Changing a checkbox on Search still requires its explicit update button.
  // Entering from Home can apply a new source snapshot to the same keyword.
  if (submitted && previous?.[0] === route.path && previous?.[1] === route.query.q) return
  const signature = JSON.stringify([q, [...searchState.sources.value].sort()])
  const currentSignature = JSON.stringify([searchState.query.value, [...searchState.resultSources.value].sort()])
  if (searchState.searchRevision.value && currentSignature === signature) { submitted = signature; return }
  if (signature === submitted) return
  submitted = signature
  searchState.query.value = q
  void searchState.search()
}, { immediate: true })
</script>
<template></template>
