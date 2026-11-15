<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useCoreClient } from '../../composables/useCoreClient'
import { routeSearchQuery } from './search-route'
const route = useRoute()
const { searchState } = useCoreClient()
// 根生命周期持有搜索状态，普通路由切换不会重建请求。
watch([() => route.path, () => route.query.q, () => searchState.sources.value.join('|')], () => {
  const q = routeSearchQuery(route.query.q)
  if (route.path !== '/search') return
  if (!q) {
    searchState.clear()
    return
  }
  if (!searchState.sources.value.length) return
  const signature = JSON.stringify([q, [...searchState.sources.value].sort()])
  const currentSignature = JSON.stringify([searchState.query.value, [...searchState.resultSources.value].sort()])
  if (searchState.searchRevision.value && currentSignature === signature) return
  searchState.query.value = q
  void searchState.search()
}, { immediate: true })
</script>
<template></template>
